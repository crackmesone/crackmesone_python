#!/usr/bin/env python3
"""
Database Sanitization Script for crackmesone_reviewer_tool

This script scans the database for incorrect or corrupted states and can fix them.
Default behavior is dry-run mode - it reports issues without making changes.

Issues detected:
1. Orphaned crackmes - crackmes whose author is non-existent
2. Orphaned solutions - solutions whose user or crackme is non-existent
3. Orphaned comments - comments whose user or crackme is non-existent
4. Orphaned notifications - notifications whose user is non-existent
5. Orphaned difficulty ratings - ratings whose user or crackme is non-existent
6. Orphaned quality ratings - ratings whose user or crackme is non-existent
7. Users with same username but different capitalization
8. Users with same email but different capitalization
9. Crackmes that do not physically exist on disk (in static directory)
10. Solutions that do not physically exist on disk (in static directory)
11. Files on disk without corresponding database entries (static and tmp directories)
    - Checks both static/crackme and tmp/crackme for orphaned crackme files
    - Checks both static/solution and tmp/solution for orphaned solution files
12. Invalid ObjectIds in database fields
13. Missing required fields in documents
14. Invisible crackmes with files in static directory (should only be in tmp for pending review)

Usage:
    python scripts/sanitize_database.py                # Dry run (default)
    python scripts/sanitize_database.py --execute     # Actually perform fixes
    python scripts/sanitize_database.py --help        # Show help
"""

import argparse
import os
import sys
import json
import datetime
from collections import defaultdict
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId

# Load environment variables
load_dotenv()

CRACKMESONE_DIR = os.getenv("CRACKMESONE_DIR")
DEFAULT_MONGODB_HOST = os.getenv("MONGODB_HOST", "127.0.0.1")
DEFAULT_MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
DEFAULT_DATABASE_NAME = os.getenv("DATABASE_NAME", "crackmesone")

class DatabaseSanitizer:
    def __init__(self, dry_run=True, mongodb_host=None, mongodb_port=None, database_name=None):
        self.dry_run = dry_run
        self.issues = []
        self.fixes_applied = []
        
        # Use provided values or defaults
        self.mongodb_host = mongodb_host or DEFAULT_MONGODB_HOST
        self.mongodb_port = mongodb_port or DEFAULT_MONGODB_PORT
        self.database_name = database_name or DEFAULT_DATABASE_NAME
        
        # Connect to MongoDB
        try:
            self.client = MongoClient(self.mongodb_host, self.mongodb_port)
            self.db = self.client[self.database_name]
            print(f"Connected to MongoDB at {self.mongodb_host}:{self.mongodb_port}")
        except Exception as e:
            print(f"Error connecting to MongoDB: {e}")
            sys.exit(1)
            
        # Verify collections exist
        self.collections = {
            'user': self.db.user,
            'crackme': self.db.crackme,
            'solution': self.db.solution,
            'comment': self.db.comment,
            'notifications': self.db.notifications,
            'rating_difficulty': self.db.rating_difficulty,
            'rating_quality': self.db.rating_quality
        }
        
        # Verify CRACKMESONE_DIR exists
        if not CRACKMESONE_DIR or not os.path.exists(CRACKMESONE_DIR):
            print(f"Error: CRACKMESONE_DIR '{CRACKMESONE_DIR}' does not exist")
            sys.exit(1)
            
        self.crackme_dir = os.path.join(CRACKMESONE_DIR, "static", "crackme")
        self.solution_dir = os.path.join(CRACKMESONE_DIR, "static", "solution")
        self.tmp_crackme_dir = os.path.join(CRACKMESONE_DIR, "tmp", "crackme")
        self.tmp_solution_dir = os.path.join(CRACKMESONE_DIR, "tmp", "solution")

        # Create directories if they don't exist
        os.makedirs(self.crackme_dir, exist_ok=True)
        os.makedirs(self.solution_dir, exist_ok=True)
        os.makedirs(self.tmp_crackme_dir, exist_ok=True)
        os.makedirs(self.tmp_solution_dir, exist_ok=True)

    def log_issue(self, category, description, severity="WARNING"):
        """Log an issue found during scanning"""
        issue = {
            'category': category,
            'description': description,
            'severity': severity,
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.issues.append(issue)
        print(f"[{severity}] {category}: {description}")

    def log_fix(self, description):
        """Log a fix that was applied"""
        fix = {
            'description': description,
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.fixes_applied.append(fix)
        print(f"[FIXED] {description}")

    def backup_database(self):
        """Create a backup of the database before making changes"""
        if self.dry_run:
            print("[DRY RUN] Would create database backup")
            return
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"/tmp/db_backup_{timestamp}"
        os.makedirs(backup_dir, exist_ok=True)
        
        try:
            for collection_name in self.collections.keys():
                collection = self.collections[collection_name]
                documents = list(collection.find())
                
                backup_file = os.path.join(backup_dir, f"{collection_name}.json")
                with open(backup_file, 'w') as f:
                    # Convert ObjectId to string for JSON serialization
                    for doc in documents:
                        if '_id' in doc:
                            doc['_id'] = str(doc['_id'])
                        if 'crackmeid' in doc and isinstance(doc['crackmeid'], ObjectId):
                            doc['crackmeid'] = str(doc['crackmeid'])
                        # Handle ObjectId fields in new collections
                        if 'objectid' in doc and isinstance(doc['objectid'], ObjectId):
                            doc['objectid'] = str(doc['objectid'])
                    json.dump(documents, f, indent=2, default=str)
                    
            print(f"Database backup created in: {backup_dir}")
            return backup_dir
            
        except Exception as e:
            print(f"Error creating backup: {e}")
            return None

    def get_all_users(self):
        """Get all users from database"""
        try:
            return list(self.collections['user'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching users: {e}", "ERROR")
            return []

    def get_all_crackmes(self):
        """Get all crackmes from database"""
        try:
            return list(self.collections['crackme'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching crackmes: {e}", "ERROR")
            return []

    def get_all_solutions(self):
        """Get all solutions from database"""
        try:
            return list(self.collections['solution'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching solutions: {e}", "ERROR")
            return []

    def get_all_comments(self):
        """Get all comments from database"""
        try:
            return list(self.collections['comment'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching comments: {e}", "ERROR")
            return []

    def get_all_notifications(self):
        """Get all notifications from database"""
        try:
            return list(self.collections['notifications'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching notifications: {e}", "ERROR")
            return []

    def get_all_rating_difficulty(self):
        """Get all difficulty ratings from database"""
        try:
            return list(self.collections['rating_difficulty'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching difficulty ratings: {e}", "ERROR")
            return []

    def get_all_rating_quality(self):
        """Get all quality ratings from database"""
        try:
            return list(self.collections['rating_quality'].find())
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error fetching quality ratings: {e}", "ERROR")
            return []

    def get_cascade_deletions_for_crackme(self, crackme_id):
        """Get all records that need to be deleted when a crackme is deleted"""
        crackme_hexid = str(crackme_id)
        
        cascade_deletions = {
            'solutions': [],
            'comments': [],
            'difficulty_ratings': [],
            'quality_ratings': []
        }
        
        try:
            # Find solutions that reference this crackme
            solutions = self.collections['solution'].find({'crackmeid': crackme_id})
            cascade_deletions['solutions'] = list(solutions)
            
            # Find comments that reference this crackme
            comments = self.collections['comment'].find({'crackmehexid': crackme_hexid})
            cascade_deletions['comments'] = list(comments)
            
            # Find difficulty ratings that reference this crackme
            difficulty_ratings = self.collections['rating_difficulty'].find({'crackmehexid': crackme_hexid})
            cascade_deletions['difficulty_ratings'] = list(difficulty_ratings)
            
            # Find quality ratings that reference this crackme
            quality_ratings = self.collections['rating_quality'].find({'crackmehexid': crackme_hexid})
            cascade_deletions['quality_ratings'] = list(quality_ratings)
            
        except Exception as e:
            self.log_issue("DATABASE_ERROR", f"Error finding cascade deletions for crackme {crackme_id}: {e}", "ERROR")
        
        return cascade_deletions

    def check_orphaned_crackmes(self):
        """Check for crackmes whose author is non-existent"""
        print("\n=== Checking for orphaned crackmes ===")
        
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        
        # Create a set of valid usernames/emails for quick lookup
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
        
        orphaned_crackmes = []
        for crackme in crackmes:
            author = crackme.get('author', '')
            if author and author not in valid_users:
                orphaned_crackmes.append(crackme)
                self.log_issue("ORPHANED_CRACKME", 
                             f"Crackme {crackme.get('_id')} has non-existent author '{author}'")
        
        if orphaned_crackmes and not self.dry_run:
            # Delete orphaned crackmes and cascade delete related records
            for crackme in orphaned_crackmes:
                try:
                    crackme_id = crackme['_id']
                    
                    # Get all related records that need to be deleted
                    cascade_deletions = self.get_cascade_deletions_for_crackme(crackme_id)
                    
                    # Delete related records first
                    for solution in cascade_deletions['solutions']:
                        self.collections['solution'].delete_one({'_id': solution['_id']})
                        self.log_fix(f"Cascade deleted solution {solution['_id']} (related to crackme {crackme_id})")
                    
                    for comment in cascade_deletions['comments']:
                        self.collections['comment'].delete_one({'_id': comment['_id']})
                        self.log_fix(f"Cascade deleted comment {comment['_id']} (related to crackme {crackme_id})")
                    
                    for rating in cascade_deletions['difficulty_ratings']:
                        self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Cascade deleted difficulty rating {rating['_id']} (related to crackme {crackme_id})")
                    
                    for rating in cascade_deletions['quality_ratings']:
                        self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Cascade deleted quality rating {rating['_id']} (related to crackme {crackme_id})")
                    
                    # Finally delete the crackme itself
                    self.collections['crackme'].delete_one({'_id': crackme_id})
                    self.log_fix(f"Deleted orphaned crackme {crackme_id}")
                    
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete crackme {crackme['_id']}: {e}", "ERROR")
        
        return len(orphaned_crackmes)

    def check_orphaned_solutions(self):
        """Check for solutions whose user or crackme is non-existent"""
        print("\n=== Checking for orphaned solutions ===")
        
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        solutions = self.get_all_solutions()
        
        # Create lookup sets
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
                
        valid_crackme_ids = {crackme['_id'] for crackme in crackmes}
        
        orphaned_solutions = []
        for solution in solutions:
            issues_found = []
            
            # Check if author exists
            author = solution.get('author', '')
            if author and author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")
            
            # Check if crackmeid exists and is valid
            crackmeid = solution.get('crackmeid')
            if crackmeid:
                if isinstance(crackmeid, str):
                    try:
                        crackmeid = ObjectId(crackmeid)
                    except InvalidId:
                        issues_found.append("invalid crackmeid format")
                        crackmeid = None
                
                if crackmeid and crackmeid not in valid_crackme_ids:
                    issues_found.append(f"non-existent crackme '{crackmeid}'")
            else:
                issues_found.append("missing crackmeid")
            
            if issues_found:
                orphaned_solutions.append(solution)
                self.log_issue("ORPHANED_SOLUTION", 
                             f"Solution {solution.get('_id')} has issues: {', '.join(issues_found)}")
        
        if orphaned_solutions and not self.dry_run:
            for solution in orphaned_solutions:
                try:
                    self.collections['solution'].delete_one({'_id': solution['_id']})
                    self.log_fix(f"Deleted orphaned solution {solution['_id']}")
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete solution {solution['_id']}: {e}", "ERROR")
        
        return len(orphaned_solutions)

    def check_orphaned_comments(self):
        """Check for comments whose user or crackme is non-existent"""
        print("\n=== Checking for orphaned comments ===")
        
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        comments = self.get_all_comments()
        
        # Create lookup sets
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
                
        # Note: Comments reference crackmes via crackmehexid (string), not ObjectId
        valid_crackme_hexids = {str(crackme['_id']) for crackme in crackmes}
        
        orphaned_comments = []
        for comment in comments:
            issues_found = []
            
            # Check if author exists
            author = comment.get('author', '')
            if author and author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")
            
            # Check if crackmehexid exists
            crackmehexid = comment.get('crackmehexid', '')
            if crackmehexid and crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")
            elif not crackmehexid:
                issues_found.append("missing crackmehexid")
            
            if issues_found:
                orphaned_comments.append(comment)
                self.log_issue("ORPHANED_COMMENT", 
                             f"Comment {comment.get('_id')} has issues: {', '.join(issues_found)}")
        
        if orphaned_comments and not self.dry_run:
            for comment in orphaned_comments:
                try:
                    self.collections['comment'].delete_one({'_id': comment['_id']})
                    self.log_fix(f"Deleted orphaned comment {comment['_id']}")
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete comment {comment['_id']}: {e}", "ERROR")
        
        return len(orphaned_comments)

    def check_orphaned_notifications(self):
        """Check for notifications whose user is non-existent"""
        print("\n=== Checking for orphaned notifications ===")
        
        users = self.get_all_users()
        notifications = self.get_all_notifications()
        
        # Create lookup set of valid usernames
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
        
        orphaned_notifications = []
        for notification in notifications:
            user = notification.get('user', '')
            if user and user not in valid_users:
                orphaned_notifications.append(notification)
                self.log_issue("ORPHANED_NOTIFICATION", 
                             f"Notification {notification.get('_id')} has non-existent user '{user}'")
        
        if orphaned_notifications and not self.dry_run:
            for notification in orphaned_notifications:
                try:
                    self.collections['notifications'].delete_one({'_id': notification['_id']})
                    self.log_fix(f"Deleted orphaned notification {notification['_id']}")
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete notification {notification['_id']}: {e}", "ERROR")
        
        return len(orphaned_notifications)

    def check_orphaned_rating_difficulty(self):
        """Check for difficulty ratings whose user or crackme is non-existent"""
        print("\n=== Checking for orphaned difficulty ratings ===")
        
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        ratings = self.get_all_rating_difficulty()
        
        # Create lookup sets
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
                
        valid_crackme_hexids = {str(crackme['_id']) for crackme in crackmes}
        
        orphaned_ratings = []
        for rating in ratings:
            issues_found = []
            
            # Check if author exists
            author = rating.get('author', '')
            if author and author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")
            
            # Check if crackmehexid exists
            crackmehexid = rating.get('crackmehexid', '')
            if crackmehexid and crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")
            elif not crackmehexid:
                issues_found.append("missing crackmehexid")
            
            if issues_found:
                orphaned_ratings.append(rating)
                self.log_issue("ORPHANED_DIFFICULTY_RATING", 
                             f"Difficulty rating {rating.get('_id')} has issues: {', '.join(issues_found)}")
        
        if orphaned_ratings and not self.dry_run:
            for rating in orphaned_ratings:
                try:
                    self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                    self.log_fix(f"Deleted orphaned difficulty rating {rating['_id']}")
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete difficulty rating {rating['_id']}: {e}", "ERROR")
        
        return len(orphaned_ratings)

    def check_orphaned_rating_quality(self):
        """Check for quality ratings whose user or crackme is non-existent"""
        print("\n=== Checking for orphaned quality ratings ===")
        
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        ratings = self.get_all_rating_quality()
        
        # Create lookup sets
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
                
        valid_crackme_hexids = {str(crackme['_id']) for crackme in crackmes}
        
        orphaned_ratings = []
        for rating in ratings:
            issues_found = []
            
            # Check if author exists
            author = rating.get('author', '')
            if author and author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")
            
            # Check if crackmehexid exists
            crackmehexid = rating.get('crackmehexid', '')
            if crackmehexid and crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")
            elif not crackmehexid:
                issues_found.append("missing crackmehexid")
            
            if issues_found:
                orphaned_ratings.append(rating)
                self.log_issue("ORPHANED_QUALITY_RATING", 
                             f"Quality rating {rating.get('_id')} has issues: {', '.join(issues_found)}")
        
        if orphaned_ratings and not self.dry_run:
            for rating in orphaned_ratings:
                try:
                    self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                    self.log_fix(f"Deleted orphaned quality rating {rating['_id']}")
                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete quality rating {rating['_id']}: {e}", "ERROR")
        
        return len(orphaned_ratings)

    def check_duplicate_users(self):
        """Check for users with same username/email but different capitalization"""
        print("\n=== Checking for duplicate users ===")
        
        users = self.get_all_users()
        
        # Group by lowercase username and email
        username_groups = defaultdict(list)
        email_groups = defaultdict(list)
        
        for user in users:
            if 'name' in user:
                username_groups[user['name'].lower()].append(user)
            if 'email' in user:
                email_groups[user['email'].lower()].append(user)
        
        # Find duplicates
        duplicate_count = 0
        
        for lowercase_username, user_list in username_groups.items():
            if len(user_list) > 1:
                duplicate_count += len(user_list) - 1
                usernames = [u['name'] for u in user_list]
                self.log_issue("DUPLICATE_USERNAME", 
                             f"Multiple users with same username (case insensitive): {usernames}")
                
                if not self.dry_run:
                    # Keep the first user, delete others
                    for user in user_list[1:]:
                        try:
                            self.collections['user'].delete_one({'_id': user['_id']})
                            self.log_fix(f"Deleted duplicate user {user['name']} ({user['_id']})")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to delete user {user['_id']}: {e}", "ERROR")
        
        for lowercase_email, user_list in email_groups.items():
            if len(user_list) > 1:
                duplicate_count += len(user_list) - 1  
                emails = [u['email'] for u in user_list]
                self.log_issue("DUPLICATE_EMAIL", 
                             f"Multiple users with same email (case insensitive): {emails}")
                
                if not self.dry_run:
                    # Keep the first user, delete others
                    for user in user_list[1:]:
                        try:
                            self.collections['user'].delete_one({'_id': user['_id']})
                            self.log_fix(f"Deleted duplicate user {user['email']} ({user['_id']})")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to delete user {user['_id']}: {e}", "ERROR")
        
        return duplicate_count

    def check_missing_files(self):
        """Check for database entries without corresponding files on disk"""
        print("\n=== Checking for missing files on disk ===")
        
        missing_files = 0
        
        # Check crackmes
        crackmes = self.get_all_crackmes()
        for crackme in crackmes:
            crackme_id = str(crackme['_id'])
            file_path = os.path.join(self.crackme_dir, f"{crackme_id}.zip")
            
            if not os.path.exists(file_path):
                missing_files += 1
                self.log_issue("MISSING_FILE", f"Crackme file missing: {file_path}")
                
                if not self.dry_run:
                    # Get all related records that need to be deleted
                    cascade_deletions = self.get_cascade_deletions_for_crackme(crackme['_id'])
                    
                    # Delete related records first
                    for solution in cascade_deletions['solutions']:
                        try:
                            self.collections['solution'].delete_one({'_id': solution['_id']})
                            self.log_fix(f"Cascade deleted solution {solution['_id']} (crackme file {crackme_id} missing)")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to cascade delete solution {solution['_id']}: {e}", "ERROR")
                    
                    for comment in cascade_deletions['comments']:
                        try:
                            self.collections['comment'].delete_one({'_id': comment['_id']})
                            self.log_fix(f"Cascade deleted comment {comment['_id']} (crackme file {crackme_id} missing)")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to cascade delete comment {comment['_id']}: {e}", "ERROR")
                    
                    for rating in cascade_deletions['difficulty_ratings']:
                        try:
                            self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                            self.log_fix(f"Cascade deleted difficulty rating {rating['_id']} (crackme file {crackme_id} missing)")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to cascade delete difficulty rating {rating['_id']}: {e}", "ERROR")
                    
                    for rating in cascade_deletions['quality_ratings']:
                        try:
                            self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                            self.log_fix(f"Cascade deleted quality rating {rating['_id']} (crackme file {crackme_id} missing)")
                        except Exception as e:
                            self.log_issue("FIX_ERROR", f"Failed to cascade delete quality rating {rating['_id']}: {e}", "ERROR")
                    
                    # Finally delete the crackme database entry
                    try:
                        self.collections['crackme'].delete_one({'_id': crackme['_id']})
                        self.log_fix(f"Deleted database entry for missing crackme file {crackme_id}")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete crackme {crackme_id}: {e}", "ERROR")
        
        # Check solutions
        solutions = self.get_all_solutions()
        for solution in solutions:
            solution_id = str(solution['_id'])
            file_path = os.path.join(self.solution_dir, f"{solution_id}.zip")
            
            if not os.path.exists(file_path):
                missing_files += 1
                self.log_issue("MISSING_FILE", f"Solution file missing: {file_path}")
                
                if not self.dry_run:
                    # Delete the database entry for missing files
                    try:
                        self.collections['solution'].delete_one({'_id': solution['_id']})
                        self.log_fix(f"Deleted database entry for missing solution file {solution_id}")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete solution {solution_id}: {e}", "ERROR")
        
        return missing_files

    def check_orphaned_files(self):
        """Check for files on disk without corresponding database entries"""
        print("\n=== Checking for orphaned files on disk ===")

        orphaned_files = 0
        orphaned_static_files = 0
        orphaned_tmp_files = 0

        # Get database IDs
        crackme_ids = {str(c['_id']) for c in self.get_all_crackmes()}
        solution_ids = {str(s['_id']) for s in self.get_all_solutions()}

        # Also get hexids for checking pending submissions in tmp
        crackme_hexids = {c.get('hexid', str(c['_id'])) for c in self.get_all_crackmes()}
        solution_hexids = {s.get('hexid', str(s['_id'])) for s in self.get_all_solutions()}

        # Check static crackme files (approved submissions)
        print("Checking static/crackme directory...")
        if os.path.exists(self.crackme_dir):
            for filename in os.listdir(self.crackme_dir):
                if filename.endswith('.zip'):
                    file_id = filename[:-4]  # Remove .zip extension
                    if file_id not in crackme_ids:
                        orphaned_files += 1
                        orphaned_static_files += 1
                        file_path = os.path.join(self.crackme_dir, filename)
                        self.log_issue("ORPHANED_STATIC_FILE", f"Crackme file without database entry: {file_path}")

                        if not self.dry_run:
                            try:
                                os.remove(file_path)
                                self.log_fix(f"Deleted orphaned crackme file {filename}")
                            except Exception as e:
                                self.log_issue("FIX_ERROR", f"Failed to delete file {file_path}: {e}", "ERROR")

        # Check static solution files (approved submissions)
        print("Checking static/solution directory...")
        if os.path.exists(self.solution_dir):
            for filename in os.listdir(self.solution_dir):
                if filename.endswith('.zip'):
                    file_id = filename[:-4]  # Remove .zip extension
                    if file_id not in solution_ids:
                        orphaned_files += 1
                        orphaned_static_files += 1
                        file_path = os.path.join(self.solution_dir, filename)
                        self.log_issue("ORPHANED_STATIC_FILE", f"Solution file without database entry: {file_path}")

                        if not self.dry_run:
                            try:
                                os.remove(file_path)
                                self.log_fix(f"Deleted orphaned solution file {filename}")
                            except Exception as e:
                                self.log_issue("FIX_ERROR", f"Failed to delete file {file_path}: {e}", "ERROR")

        # Check tmp crackme files (pending submissions)
        # These files have format: username+++hexid+++filename
        print("Checking tmp/crackme directory...")
        if os.path.exists(self.tmp_crackme_dir):
            for filename in os.listdir(self.tmp_crackme_dir):
                if '+++' in filename:
                    try:
                        parts = filename.split('+++')
                        if len(parts) >= 2:
                            username, hexid = parts[0], parts[1]
                            if hexid not in crackme_hexids:
                                orphaned_files += 1
                                orphaned_tmp_files += 1
                                file_path = os.path.join(self.tmp_crackme_dir, filename)
                                self.log_issue("ORPHANED_TMP_FILE",
                                             f"Tmp crackme file without database entry: {file_path} (hexid: {hexid})")

                                if not self.dry_run:
                                    try:
                                        os.remove(file_path)
                                        self.log_fix(f"Deleted orphaned tmp crackme file {filename}")
                                    except Exception as e:
                                        self.log_issue("FIX_ERROR", f"Failed to delete file {file_path}: {e}", "ERROR")
                    except Exception as e:
                        self.log_issue("PARSE_ERROR", f"Failed to parse tmp filename {filename}: {e}", "WARNING")

        # Check tmp solution files (pending submissions)
        print("Checking tmp/solution directory...")
        if os.path.exists(self.tmp_solution_dir):
            for filename in os.listdir(self.tmp_solution_dir):
                if '+++' in filename:
                    try:
                        parts = filename.split('+++')
                        if len(parts) >= 2:
                            username, hexid = parts[0], parts[1]
                            if hexid not in solution_hexids:
                                orphaned_files += 1
                                orphaned_tmp_files += 1
                                file_path = os.path.join(self.tmp_solution_dir, filename)
                                self.log_issue("ORPHANED_TMP_FILE",
                                             f"Tmp solution file without database entry: {file_path} (hexid: {hexid})")

                                if not self.dry_run:
                                    try:
                                        os.remove(file_path)
                                        self.log_fix(f"Deleted orphaned tmp solution file {filename}")
                                    except Exception as e:
                                        self.log_issue("FIX_ERROR", f"Failed to delete file {file_path}: {e}", "ERROR")
                    except Exception as e:
                        self.log_issue("PARSE_ERROR", f"Failed to parse tmp filename {filename}: {e}", "WARNING")

        print(f"Found {orphaned_static_files} orphaned files in static directories")
        print(f"Found {orphaned_tmp_files} orphaned files in tmp directories")

        return orphaned_files

    def check_data_integrity(self):
        """Check for data integrity issues like invalid ObjectIds and missing required fields"""
        print("\n=== Checking data integrity ===")
        
        integrity_issues = 0
        
        # Check solutions for invalid crackmeid
        solutions = self.get_all_solutions()
        for solution in solutions:
            crackmeid = solution.get('crackmeid')
            if crackmeid:
                if isinstance(crackmeid, str):
                    try:
                        ObjectId(crackmeid)
                    except InvalidId:
                        integrity_issues += 1
                        self.log_issue("INVALID_OBJECTID", 
                                     f"Solution {solution['_id']} has invalid crackmeid: {crackmeid}")
                        
                        if not self.dry_run:
                            try:
                                self.collections['solution'].delete_one({'_id': solution['_id']})
                                self.log_fix(f"Deleted solution with invalid crackmeid {solution['_id']}")
                            except Exception as e:
                                self.log_issue("FIX_ERROR", f"Failed to delete solution {solution['_id']}: {e}", "ERROR")
            else:
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Solution {solution['_id']} missing crackmeid field")
                if not self.dry_run:
                    try:
                        self.collections['solution'].delete_one({'_id': solution['_id']})
                        self.log_fix(f"Deleted solution with missing crackmeid {solution['_id']}")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete solution {solution['_id']}: {e}", "ERROR")
        
        # Check for required fields
        users = self.get_all_users()
        for user in users:
            if not user.get('email'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"User {user['_id']} missing email field")
        
        crackmes = self.get_all_crackmes()
        for crackme in crackmes:
            if not crackme.get('author'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Crackme {crackme['_id']} missing author field")
        
        comments = self.get_all_comments()
        for comment in comments:
            if not comment.get('author'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Comment {comment['_id']} missing author field")
                if not self.dry_run:
                    try:
                        self.collections['comment'].delete_one({'_id': comment['_id']})
                        self.log_fix(f"Deleted comment {comment['_id']} with missing author field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete comment {comment['_id']}: {e}", "ERROR")
            elif not comment.get('crackmehexid'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Comment {comment['_id']} missing crackmehexid field")
                if not self.dry_run:
                    try:
                        self.collections['comment'].delete_one({'_id': comment['_id']})
                        self.log_fix(f"Deleted comment {comment['_id']} with missing crackmehexid field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete comment {comment['_id']}: {e}", "ERROR")
        
        # Check notifications for required fields
        notifications = self.get_all_notifications()
        for notification in notifications:
            if not notification.get('user'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Notification {notification['_id']} missing user field")
        
        # Check difficulty ratings for required fields
        difficulty_ratings = self.get_all_rating_difficulty()
        for rating in difficulty_ratings:
            if not rating.get('author'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Difficulty rating {rating['_id']} missing author field")
                if not self.dry_run:
                    try:
                        self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Deleted difficulty rating {rating['_id']} with missing author field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete difficulty rating {rating['_id']}: {e}", "ERROR")
            elif not rating.get('crackmehexid'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Difficulty rating {rating['_id']} missing crackmehexid field")
                if not self.dry_run:
                    try:
                        self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Deleted difficulty rating {rating['_id']} with missing crackmehexid field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete difficulty rating {rating['_id']}: {e}", "ERROR")
        
        # Check quality ratings for required fields
        quality_ratings = self.get_all_rating_quality()
        for rating in quality_ratings:
            if not rating.get('author'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Quality rating {rating['_id']} missing author field")
                if not self.dry_run:
                    try:
                        self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Deleted quality rating {rating['_id']} with missing author field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete quality rating {rating['_id']}: {e}", "ERROR")
            elif not rating.get('crackmehexid'):
                integrity_issues += 1
                self.log_issue("MISSING_FIELD", f"Quality rating {rating['_id']} missing crackmehexid field")
                if not self.dry_run:
                    try:
                        self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Deleted quality rating {rating['_id']} with missing crackmehexid field")
                    except Exception as e:
                        self.log_issue("FIX_ERROR", f"Failed to delete quality rating {rating['_id']}: {e}", "ERROR")
        
        return integrity_issues

    def check_invisible_crackmes(self):
        """Check for invisible crackmes that have files in static directory"""
        print("\n=== Checking for invisible crackmes in static directory ===")

        crackmes = self.get_all_crackmes()
        inconsistent_invisible_crackmes = []

        for crackme in crackmes:
            # Check if crackme is invisible (visible field is False or missing)
            visible = crackme.get('visible', True)  # Default to True if not specified

            if not visible:
                # Crackme is invisible, check where its file is located
                crackme_id = str(crackme['_id'])
                static_file_path = os.path.join(self.crackme_dir, f"{crackme_id}.zip")
                tmp_file_path = None

                # Check if file exists in tmp directory (pending review)
                # Tmp files have format: username+++hexid+++filename
                if os.path.exists(self.tmp_crackme_dir):
                    for filename in os.listdir(self.tmp_crackme_dir):
                        if '+++' in filename and crackme_id in filename:
                            tmp_file_path = os.path.join(self.tmp_crackme_dir, filename)
                            break

                # If file is in static directory, it's inconsistent
                if os.path.exists(static_file_path):
                    inconsistent_invisible_crackmes.append(crackme)
                    if tmp_file_path:
                        self.log_issue("INVISIBLE_CRACKME_IN_STATIC",
                                     f"Invisible crackme {crackme_id} has file in static directory (also found in tmp - should only be in tmp for pending review)")
                    else:
                        self.log_issue("INVISIBLE_CRACKME_IN_STATIC",
                                     f"Invisible crackme {crackme_id} has file in static directory but not in tmp (inconsistent state)")

        if inconsistent_invisible_crackmes and not self.dry_run:
            for crackme in inconsistent_invisible_crackmes:
                try:
                    crackme_id = str(crackme['_id'])
                    static_file_path = os.path.join(self.crackme_dir, f"{crackme_id}.zip")

                    # Get all related records that need to be deleted
                    cascade_deletions = self.get_cascade_deletions_for_crackme(crackme['_id'])

                    # Delete related records first
                    for solution in cascade_deletions['solutions']:
                        self.collections['solution'].delete_one({'_id': solution['_id']})
                        self.log_fix(f"Cascade deleted solution {solution['_id']} (invisible crackme {crackme_id} in static)")

                    for comment in cascade_deletions['comments']:
                        self.collections['comment'].delete_one({'_id': comment['_id']})
                        self.log_fix(f"Cascade deleted comment {comment['_id']} (invisible crackme {crackme_id} in static)")

                    for rating in cascade_deletions['difficulty_ratings']:
                        self.collections['rating_difficulty'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Cascade deleted difficulty rating {rating['_id']} (invisible crackme {crackme_id} in static)")

                    for rating in cascade_deletions['quality_ratings']:
                        self.collections['rating_quality'].delete_one({'_id': rating['_id']})
                        self.log_fix(f"Cascade deleted quality rating {rating['_id']} (invisible crackme {crackme_id} in static)")

                    # Delete the static file
                    if os.path.exists(static_file_path):
                        os.remove(static_file_path)
                        self.log_fix(f"Deleted static file for invisible crackme {crackme_id}")

                    # Delete the crackme database entry
                    self.collections['crackme'].delete_one({'_id': crackme['_id']})
                    self.log_fix(f"Deleted invisible crackme {crackme_id} from database")

                except Exception as e:
                    self.log_issue("FIX_ERROR", f"Failed to delete invisible crackme {crackme['_id']}: {e}", "ERROR")

        return len(inconsistent_invisible_crackmes)

    def plan_operations(self):
        """Analyze the database and plan all operations that will be performed"""
        print("\n" + "="*60)
        print("PLANNED DATABASE OPERATIONS")
        print("="*60)
        
        # Collect all planned operations
        planned_operations = {
            'crackme_deletions': [],
            'solution_deletions': [],
            'comment_deletions': [],
            'notification_deletions': [],
            'difficulty_rating_deletions': [],
            'quality_rating_deletions': [],
            'user_deletions': [],
            'file_deletions': [],
            'missing_file_crackme_cascade_deletions': [],
            'missing_file_solution_deletions': [],
            'orphaned_static_files': [],
            'orphaned_tmp_files': [],
            'integrity_fixes': [],
            'invisible_crackme_cascade_deletions': []
        }
        
        # Get all data first
        users = self.get_all_users()
        crackmes = self.get_all_crackmes()
        solutions = self.get_all_solutions()
        comments = self.get_all_comments()
        notifications = self.get_all_notifications()
        difficulty_ratings = self.get_all_rating_difficulty()
        quality_ratings = self.get_all_rating_quality()
        
        # Create lookup sets
        valid_users = set()
        for user in users:
            if 'name' in user:
                valid_users.add(user['name'])
            if 'email' in user:
                valid_users.add(user['email'])
        
        valid_crackme_ids = {crackme['_id'] for crackme in crackmes}
        valid_crackme_hexids = {str(crackme['_id']) for crackme in crackmes}
        
        # Check for orphaned crackmes (non-existent authors)
        for crackme in crackmes:
            author = crackme.get('author', '')
            if author and author not in valid_users:
                crackme_id = crackme['_id']
                planned_operations['crackme_deletions'].append({
                    'id': crackme_id,
                    'author': author,
                    'reason': f'non-existent author "{author}"'
                })
                
                # Get cascade deletions for this crackme
                cascade_deletions = self.get_cascade_deletions_for_crackme(crackme_id)
                
                for solution in cascade_deletions['solutions']:
                    planned_operations['solution_deletions'].append({
                        'id': solution['_id'],
                        'reason': f'cascade delete (crackme {crackme_id} being deleted for orphaned author)'
                    })
                
                for comment in cascade_deletions['comments']:
                    planned_operations['comment_deletions'].append({
                        'id': comment['_id'],
                        'reason': f'cascade delete (crackme {crackme_id} being deleted for orphaned author)'
                    })
                
                for rating in cascade_deletions['difficulty_ratings']:
                    planned_operations['difficulty_rating_deletions'].append({
                        'id': rating['_id'],
                        'reason': f'cascade delete (crackme {crackme_id} being deleted for orphaned author)'
                    })
                
                for rating in cascade_deletions['quality_ratings']:
                    planned_operations['quality_rating_deletions'].append({
                        'id': rating['_id'],
                        'reason': f'cascade delete (crackme {crackme_id} being deleted for orphaned author)'
                    })

        # Check for invisible crackmes in static directory
        for crackme in crackmes:
            visible = crackme.get('visible', True)
            if not visible:
                crackme_id = str(crackme['_id'])
                static_file_path = os.path.join(self.crackme_dir, f"{crackme_id}.zip")

                # If file is in static directory, it's inconsistent (should only be in tmp for pending review)
                if os.path.exists(static_file_path):
                    # Skip if already planned for deletion
                    if not any(op['id'] == crackme['_id'] for op in planned_operations['crackme_deletions']):
                        planned_operations['invisible_crackme_cascade_deletions'].append({
                            'crackme_id': crackme['_id'],
                            'file_path': static_file_path,
                            'reason': f'invisible crackme {crackme_id} has file in static directory (should only be in tmp for pending review)'
                        })

                        # Get cascade deletions for this invisible crackme
                        cascade_deletions = self.get_cascade_deletions_for_crackme(crackme['_id'])

                        for solution in cascade_deletions['solutions']:
                            planned_operations['solution_deletions'].append({
                                'id': solution['_id'],
                                'reason': f'cascade delete (invisible crackme {crackme_id} in static)'
                            })

                        for comment in cascade_deletions['comments']:
                            planned_operations['comment_deletions'].append({
                                'id': comment['_id'],
                                'reason': f'cascade delete (invisible crackme {crackme_id} in static)'
                            })

                        for rating in cascade_deletions['difficulty_ratings']:
                            planned_operations['difficulty_rating_deletions'].append({
                                'id': rating['_id'],
                                'reason': f'cascade delete (invisible crackme {crackme_id} in static)'
                            })

                        for rating in cascade_deletions['quality_ratings']:
                            planned_operations['quality_rating_deletions'].append({
                                'id': rating['_id'],
                                'reason': f'cascade delete (invisible crackme {crackme_id} in static)'
                            })

        # Check for missing crackme files
        for crackme in crackmes:
            crackme_id = str(crackme['_id'])
            file_path = os.path.join(self.crackme_dir, f"{crackme_id}.zip")
            
            if not os.path.exists(file_path):
                # Skip if already planned for deletion due to orphaned author
                if not any(op['id'] == crackme['_id'] for op in planned_operations['crackme_deletions']):
                    planned_operations['missing_file_crackme_cascade_deletions'].append({
                        'crackme_id': crackme['_id'],
                        'file_path': file_path,
                        'reason': f'crackme file missing: {file_path}'
                    })
                    
                    # Get cascade deletions for this missing file crackme
                    cascade_deletions = self.get_cascade_deletions_for_crackme(crackme['_id'])
                    
                    for solution in cascade_deletions['solutions']:
                        planned_operations['solution_deletions'].append({
                            'id': solution['_id'],
                            'reason': f'cascade delete (crackme file {crackme_id} missing)'
                        })
                    
                    for comment in cascade_deletions['comments']:
                        planned_operations['comment_deletions'].append({
                            'id': comment['_id'],
                            'reason': f'cascade delete (crackme file {crackme_id} missing)'
                        })
                    
                    for rating in cascade_deletions['difficulty_ratings']:
                        planned_operations['difficulty_rating_deletions'].append({
                            'id': rating['_id'],
                            'reason': f'cascade delete (crackme file {crackme_id} missing)'
                        })
                    
                    for rating in cascade_deletions['quality_ratings']:
                        planned_operations['quality_rating_deletions'].append({
                            'id': rating['_id'],
                            'reason': f'cascade delete (crackme file {crackme_id} missing)'
                        })
        
        # Check for missing solution files
        for solution in solutions:
            solution_id = str(solution['_id'])
            file_path = os.path.join(self.solution_dir, f"{solution_id}.zip")
            
            if not os.path.exists(file_path):
                # Skip if already planned for deletion
                if not any(op['id'] == solution['_id'] for op in planned_operations['solution_deletions']):
                    planned_operations['missing_file_solution_deletions'].append({
                        'id': solution['_id'],
                        'file_path': file_path,
                        'reason': f'solution file missing: {file_path}'
                    })
        
        # Check for orphaned solutions (not related to crackme deletions)
        for solution in solutions:
            # Skip solutions that will be cascade deleted
            if any(sol['id'] == solution['_id'] for sol in planned_operations['solution_deletions']):
                continue
                
            issues_found = []
            author = solution.get('author', '')
            if author and author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")
            
            crackmeid = solution.get('crackmeid')
            if crackmeid:
                if isinstance(crackmeid, str):
                    try:
                        crackmeid = ObjectId(crackmeid)
                    except InvalidId:
                        issues_found.append("invalid crackmeid format")
                        crackmeid = None
                
                if crackmeid and crackmeid not in valid_crackme_ids:
                    issues_found.append(f"non-existent crackme '{crackmeid}'")
            else:
                issues_found.append("missing crackmeid")
            
            if issues_found:
                planned_operations['solution_deletions'].append({
                    'id': solution['_id'],
                    'reason': f"orphaned solution: {', '.join(issues_found)}"
                })

        # Check for orphaned comments (not related to crackme deletions)
        for comment in comments:
            # Skip comments that will be cascade deleted
            if any(c['id'] == comment['_id'] for c in planned_operations['comment_deletions']):
                continue

            issues_found = []
            author = comment.get('author', '')
            if not author:
                issues_found.append("missing author field")
            elif author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")

            crackmehexid = comment.get('crackmehexid', '')
            if not crackmehexid:
                issues_found.append("missing crackmehexid field")
            elif crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")

            if issues_found:
                planned_operations['comment_deletions'].append({
                    'id': comment['_id'],
                    'reason': f"orphaned/invalid comment: {', '.join(issues_found)}"
                })

        # Check for orphaned notifications
        for notification in notifications:
            user = notification.get('user', '')
            if not user:
                planned_operations['notification_deletions'].append({
                    'id': notification['_id'],
                    'reason': "missing user field"
                })
            elif user not in valid_users:
                planned_operations['notification_deletions'].append({
                    'id': notification['_id'],
                    'reason': f"non-existent user '{user}'"
                })

        # Check for orphaned difficulty ratings (not related to crackme deletions)
        for rating in difficulty_ratings:
            # Skip ratings that will be cascade deleted
            if any(r['id'] == rating['_id'] for r in planned_operations['difficulty_rating_deletions']):
                continue

            issues_found = []
            author = rating.get('author', '')
            if not author:
                issues_found.append("missing author field")
            elif author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")

            crackmehexid = rating.get('crackmehexid', '')
            if not crackmehexid:
                issues_found.append("missing crackmehexid field")
            elif crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")

            if issues_found:
                planned_operations['difficulty_rating_deletions'].append({
                    'id': rating['_id'],
                    'reason': f"orphaned/invalid difficulty rating: {', '.join(issues_found)}"
                })

        # Check for orphaned quality ratings (not related to crackme deletions)
        for rating in quality_ratings:
            # Skip ratings that will be cascade deleted
            if any(r['id'] == rating['_id'] for r in planned_operations['quality_rating_deletions']):
                continue

            issues_found = []
            author = rating.get('author', '')
            if not author:
                issues_found.append("missing author field")
            elif author not in valid_users:
                issues_found.append(f"non-existent author '{author}'")

            crackmehexid = rating.get('crackmehexid', '')
            if not crackmehexid:
                issues_found.append("missing crackmehexid field")
            elif crackmehexid not in valid_crackme_hexids:
                issues_found.append(f"non-existent crackme '{crackmehexid}'")

            if issues_found:
                planned_operations['quality_rating_deletions'].append({
                    'id': rating['_id'],
                    'reason': f"orphaned/invalid quality rating: {', '.join(issues_found)}"
                })

        # Check for duplicate users
        from collections import defaultdict
        username_groups = defaultdict(list)
        email_groups = defaultdict(list)

        for user in users:
            if 'name' in user:
                username_groups[user['name'].lower()].append(user)
            if 'email' in user:
                email_groups[user['email'].lower()].append(user)

        # Find duplicate usernames
        for lowercase_username, user_list in username_groups.items():
            if len(user_list) > 1:
                # Keep the first user, delete others
                for user in user_list[1:]:
                    planned_operations['user_deletions'].append({
                        'id': user['_id'],
                        'name': user.get('name', ''),
                        'reason': f"duplicate username (case insensitive) - keeping first occurrence"
                    })

        # Find duplicate emails
        for lowercase_email, user_list in email_groups.items():
            if len(user_list) > 1:
                # Keep the first user, delete others
                for user in user_list[1:]:
                    # Only add if not already planned for deletion due to username duplication
                    if not any(op['id'] == user['_id'] for op in planned_operations['user_deletions']):
                        planned_operations['user_deletions'].append({
                            'id': user['_id'],
                            'email': user.get('email', ''),
                            'reason': f"duplicate email (case insensitive) - keeping first occurrence"
                        })

        # Check for orphaned files on disk (both static and tmp directories)
        # Get database IDs (after planned deletions)
        remaining_crackme_ids = {str(c['_id']) for c in crackmes} - {str(op['id']) for op in planned_operations['crackme_deletions']} - {str(op['crackme_id']) for op in planned_operations['missing_file_crackme_cascade_deletions']}
        remaining_solution_ids = {str(s['_id']) for s in solutions} - {str(op['id']) for op in planned_operations['solution_deletions']} - {str(op['id']) for op in planned_operations['missing_file_solution_deletions']}
        crackme_hexids = {c.get('hexid', str(c['_id'])) for c in crackmes}
        solution_hexids = {s.get('hexid', str(s['_id'])) for s in solutions}

        # Check static crackme files
        if os.path.exists(self.crackme_dir):
            for filename in os.listdir(self.crackme_dir):
                if filename.endswith('.zip'):
                    file_id = filename[:-4]  # Remove .zip extension
                    if file_id not in remaining_crackme_ids:
                        file_path = os.path.join(self.crackme_dir, filename)
                        planned_operations['orphaned_static_files'].append({
                            'path': file_path,
                            'type': 'crackme',
                            'reason': f"orphaned crackme file without database entry: {filename}"
                        })

        # Check static solution files
        if os.path.exists(self.solution_dir):
            for filename in os.listdir(self.solution_dir):
                if filename.endswith('.zip'):
                    file_id = filename[:-4]  # Remove .zip extension
                    if file_id not in remaining_solution_ids:
                        file_path = os.path.join(self.solution_dir, filename)
                        planned_operations['orphaned_static_files'].append({
                            'path': file_path,
                            'type': 'solution',
                            'reason': f"orphaned solution file without database entry: {filename}"
                        })

        # Check tmp crackme files
        if os.path.exists(self.tmp_crackme_dir):
            for filename in os.listdir(self.tmp_crackme_dir):
                if '+++' in filename:
                    try:
                        parts = filename.split('+++')
                        if len(parts) >= 2:
                            hexid = parts[1]
                            if hexid not in crackme_hexids:
                                planned_operations['orphaned_tmp_files'].append({
                                    'path': os.path.join(self.tmp_crackme_dir, filename),
                                    'type': 'crackme',
                                    'reason': f'no database entry for hexid {hexid}'
                                })
                    except:
                        pass

        # Check tmp solution files
        if os.path.exists(self.tmp_solution_dir):
            for filename in os.listdir(self.tmp_solution_dir):
                if '+++' in filename:
                    try:
                        parts = filename.split('+++')
                        if len(parts) >= 2:
                            hexid = parts[1]
                            if hexid not in solution_hexids:
                                planned_operations['orphaned_tmp_files'].append({
                                    'path': os.path.join(self.tmp_solution_dir, filename),
                                    'type': 'solution',
                                    'reason': f'no database entry for hexid {hexid}'
                                })
                    except:
                        pass

        # Check for invalid ObjectIds in solutions
        for solution in solutions:
            # Skip solutions already planned for deletion
            if any(op['id'] == solution['_id'] for op in planned_operations['solution_deletions'] + planned_operations['missing_file_solution_deletions']):
                continue

            crackmeid = solution.get('crackmeid')
            if crackmeid and isinstance(crackmeid, str):
                try:
                    ObjectId(crackmeid)
                except InvalidId:
                    planned_operations['integrity_fixes'].append({
                        'id': solution['_id'],
                        'type': 'solution',
                        'field': 'crackmeid',
                        'reason': f"invalid crackmeid ObjectId format: {crackmeid}"
                    })

        # Print all planned operations verbosely
        total_operations = 0

        if planned_operations['crackme_deletions']:
            count = len(planned_operations['crackme_deletions'])
            total_operations += count
            print(f"\nCrackme Deletions (Orphaned Authors): {count} operations")
            for op in planned_operations['crackme_deletions']:
                print(f"  - Delete crackme {op['id']} (author: {op['author']}) - {op['reason']}")

        if planned_operations['missing_file_crackme_cascade_deletions']:
            count = len(planned_operations['missing_file_crackme_cascade_deletions'])
            total_operations += count
            print(f"\nCrackme Deletions (Missing Files): {count} operations")
            for op in planned_operations['missing_file_crackme_cascade_deletions']:
                print(f"  - Delete crackme {op['crackme_id']} and all related records - {op['reason']}")

        if planned_operations['invisible_crackme_cascade_deletions']:
            count = len(planned_operations['invisible_crackme_cascade_deletions'])
            total_operations += count
            print(f"\nCrackme Deletions (Invisible in Static): {count} operations")
            for op in planned_operations['invisible_crackme_cascade_deletions']:
                print(f"  - Delete crackme {op['crackme_id']} and all related records - {op['reason']}")

        if planned_operations['solution_deletions']:
            count = len(planned_operations['solution_deletions'])
            total_operations += count
            print(f"\nSolution Deletions: {count} operations")
            for op in planned_operations['solution_deletions']:
                print(f"  - Delete solution {op['id']} - {op['reason']}")

        if planned_operations['missing_file_solution_deletions']:
            count = len(planned_operations['missing_file_solution_deletions'])
            total_operations += count
            print(f"\nSolution Deletions (Missing Files): {count} operations")
            for op in planned_operations['missing_file_solution_deletions']:
                print(f"  - Delete solution {op['id']} - {op['reason']}")

        if planned_operations['comment_deletions']:
            count = len(planned_operations['comment_deletions'])
            total_operations += count
            print(f"\nComment Deletions: {count} operations")
            for op in planned_operations['comment_deletions']:
                print(f"  - Delete comment {op['id']} - {op['reason']}")

        if planned_operations['notification_deletions']:
            count = len(planned_operations['notification_deletions'])
            total_operations += count
            print(f"\nNotification Deletions: {count} operations")
            for op in planned_operations['notification_deletions']:
                print(f"  - Delete notification {op['id']} - {op['reason']}")

        if planned_operations['difficulty_rating_deletions']:
            count = len(planned_operations['difficulty_rating_deletions'])
            total_operations += count
            print(f"\nDifficulty Rating Deletions: {count} operations")
            for op in planned_operations['difficulty_rating_deletions']:
                print(f"  - Delete difficulty rating {op['id']} - {op['reason']}")

        if planned_operations['quality_rating_deletions']:
            count = len(planned_operations['quality_rating_deletions'])
            total_operations += count
            print(f"\nQuality Rating Deletions: {count} operations")
            for op in planned_operations['quality_rating_deletions']:
                print(f"  - Delete quality rating {op['id']} - {op['reason']}")

        if planned_operations['user_deletions']:
            count = len(planned_operations['user_deletions'])
            total_operations += count
            print(f"\nUser Deletions: {count} operations")
            for op in planned_operations['user_deletions']:
                user_info = op.get('name', op.get('email', 'unknown'))
                print(f"  - Delete user {op['id']} ({user_info}) - {op['reason']}")

        if planned_operations['file_deletions']:
            count = len(planned_operations['file_deletions'])
            total_operations += count
            print(f"\nFile Deletions: {count} operations")
            for op in planned_operations['file_deletions']:
                print(f"  - Delete {op['type']} file {op['path']} - {op['reason']}")

        if planned_operations['orphaned_static_files']:
            count = len(planned_operations['orphaned_static_files'])
            total_operations += count
            print(f"\nOrphaned Static Files: {count} operations")
            for op in planned_operations['orphaned_static_files']:
                print(f"  - Delete {op['type']} file {op['path']} - {op['reason']}")

        if planned_operations['orphaned_tmp_files']:
            count = len(planned_operations['orphaned_tmp_files'])
            total_operations += count
            print(f"\nOrphaned Tmp Files: {count} operations")
            for op in planned_operations['orphaned_tmp_files']:
                print(f"  - Delete {op['type']} file {op['path']} - {op['reason']}")

        if planned_operations['integrity_fixes']:
            count = len(planned_operations['integrity_fixes'])
            total_operations += count
            print(f"\nIntegrity Fixes (Deletions): {count} operations")
            for op in planned_operations['integrity_fixes']:
                print(f"  - Delete {op['type']} {op['id']} - {op['reason']}")
        
        if total_operations == 0:
            print("\nNo operations planned - database appears clean!")
        else:
            print(f"\nTotal operations planned: {total_operations}")
            
            if self.dry_run:
                print("\n[DRY RUN MODE] No changes will be made. Use --execute to apply these operations.")
            else:
                print("\n[EXECUTION MODE] The above operations will be performed.")
        
        print("="*60)
        return planned_operations

    def run_all_checks(self):
        """Run all sanitization checks"""
        print(f"Starting database sanitization {'(DRY RUN)' if self.dry_run else '(LIVE MODE)'}")
        print(f"Database: {self.database_name} at {self.mongodb_host}:{self.mongodb_port}")
        print(f"Static crackmes directory: {self.crackme_dir}")
        print(f"Static solutions directory: {self.solution_dir}")
        print(f"Tmp crackmes directory: {self.tmp_crackme_dir}")
        print(f"Tmp solutions directory: {self.tmp_solution_dir}")
        
        # First, plan all operations and show what will be done
        planned_operations = self.plan_operations()
        
        # Backup database if not in dry run mode
        if not self.dry_run:
            backup_path = self.backup_database()
            if not backup_path:
                print("Failed to create backup. Aborting.")
                return
        
        # Run all checks
        results = {}
        results['orphaned_crackmes'] = self.check_orphaned_crackmes()
        results['orphaned_solutions'] = self.check_orphaned_solutions()
        results['orphaned_comments'] = self.check_orphaned_comments()
        results['orphaned_notifications'] = self.check_orphaned_notifications()
        results['orphaned_difficulty_ratings'] = self.check_orphaned_rating_difficulty()
        results['orphaned_quality_ratings'] = self.check_orphaned_rating_quality()
        results['duplicate_users'] = self.check_duplicate_users()
        results['missing_files'] = self.check_missing_files()
        results['orphaned_files'] = self.check_orphaned_files()
        results['integrity_issues'] = self.check_data_integrity()
        results['invisible_crackmes_in_static'] = self.check_invisible_crackmes()
        
        # Summary
        print("\n" + "="*50)
        print("SANITIZATION SUMMARY")
        print("="*50)
        
        total_issues = sum(results.values())
        print(f"Total issues found: {total_issues}")
        
        for check_name, count in results.items():
            if count > 0:
                print(f"  {check_name.replace('_', ' ').title()}: {count}")
        
        if self.dry_run:
            print(f"\n[DRY RUN] No changes were made to the database.")
            print("Run with --execute to apply fixes.")
        else:
            print(f"\nApplied {len(self.fixes_applied)} fixes.")
            if self.fixes_applied:
                print("Fixes applied:")
                for fix in self.fixes_applied:
                    print(f"  - {fix['description']}")
        
        return total_issues


def main():
    parser = argparse.ArgumentParser(
        description="Sanitize the crackmesone database by detecting and fixing issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually perform the fixes (default is dry-run mode)'
    )
    
    parser.add_argument(
        '--mongodb-host',
        default=DEFAULT_MONGODB_HOST,
        help=f'MongoDB host (default: {DEFAULT_MONGODB_HOST})'
    )
    
    parser.add_argument(
        '--mongodb-port', 
        type=int,
        default=DEFAULT_MONGODB_PORT,
        help=f'MongoDB port (default: {DEFAULT_MONGODB_PORT})'
    )
    
    parser.add_argument(
        '--database',
        default=DEFAULT_DATABASE_NAME,
        help=f'Database name (default: {DEFAULT_DATABASE_NAME})'
    )
    
    args = parser.parse_args()
    
    # Check required environment
    if not CRACKMESONE_DIR:
        print("Error: CRACKMESONE_DIR environment variable is required")
        sys.exit(1)
    
    # Create and run sanitizer
    sanitizer = DatabaseSanitizer(
        dry_run=not args.execute,
        mongodb_host=args.mongodb_host,
        mongodb_port=args.mongodb_port,
        database_name=args.database
    )
    
    try:
        total_issues = sanitizer.run_all_checks()
        sys.exit(0 if total_issues == 0 else 1)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error during sanitization: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()