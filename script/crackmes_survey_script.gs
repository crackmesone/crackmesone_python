/**
 * Crackmes.one Community Survey - Google Apps Script
 *
 * Instructions:
 * 1. Go to https://script.google.com
 * 2. Create a new project (click "New project")
 * 3. Delete any existing code and paste this entire script
 * 4. Click the "Run" button (or press Ctrl+R)
 * 5. Authorize the script when prompted
 * 6. The form will be created in your Google Drive
 * 7. Check the execution log for the form URL
 */

function createCrackmesSurvey() {
  // Create a new form
  var form = FormApp.create('Crackmes.one Community Survey');
  form.setDescription(
    'Help us improve crackmes.one! This survey collects feedback from our community ' +
    'to better understand your needs and preferences. Your responses are valuable ' +
    'and will help shape the future of the platform.\n\n' +
    'Estimated time: 5-10 minutes'
  );
  form.setConfirmationMessage('Thank you for your feedback! Your responses will help us improve crackmes.one.');
  form.setAllowResponseEdits(false);
  form.setLimitOneResponsePerUser(false);
  form.setProgressBar(true);

  // ============================================
  // SECTION 1: User Demographics
  // ============================================
  form.addPageBreakItem()
    .setTitle('About You')
    .setHelpText('Tell us a bit about yourself and your background.');

  form.addMultipleChoiceItem()
    .setTitle('How would you describe your experience level in reverse engineering?')
    .setChoiceValues([
      'Beginner (just starting out)',
      'Intermediate (comfortable with basic challenges)',
      'Advanced (can solve most difficulty 4-5 challenges)',
      'Expert (can solve difficulty 6 challenges, develops RE tools)'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How long have you been practicing reverse engineering?')
    .setChoiceValues([
      'Less than 6 months',
      '6 months to 1 year',
      '1 to 3 years',
      '3 to 5 years',
      'More than 5 years'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('What is your primary motivation for using crackmes.one? (Select all that apply)')
    .setChoiceValues([
      'Learning reverse engineering',
      'Practicing and improving skills',
      'Preparing for CTF competitions',
      'Professional development / career',
      'Fun and entertainment',
      'Creating challenges for others',
      'Academic research or coursework'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How did you discover crackmes.one?')
    .setChoiceValues([
      'Search engine (Google, etc.)',
      'Social media (Reddit, Twitter, etc.)',
      'Friend or colleague recommendation',
      'Online course or tutorial',
      'CTF community',
      'Other'
    ])
    .setRequired(false);

  // ============================================
  // SECTION 2: Platform Usage & Experience
  // ============================================
  form.addPageBreakItem()
    .setTitle('Your Experience with Crackmes.one')
    .setHelpText('Tell us about how you use the platform.');

  form.addMultipleChoiceItem()
    .setTitle('How often do you visit crackmes.one?')
    .setChoiceValues([
      'Daily',
      'Several times a week',
      'Weekly',
      'A few times a month',
      'Rarely (once a month or less)',
      'This is my first time'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How long have you been using crackmes.one?')
    .setChoiceValues([
      'Less than 1 month',
      '1 to 6 months',
      '6 months to 1 year',
      '1 to 2 years',
      'More than 2 years'
    ])
    .setRequired(true);

  form.addScaleItem()
    .setTitle('How satisfied are you with crackmes.one overall?')
    .setBounds(1, 5)
    .setLabels('Very Dissatisfied', 'Very Satisfied')
    .setRequired(true);

  form.addScaleItem()
    .setTitle('How easy is it to find challenges that match your skill level?')
    .setBounds(1, 5)
    .setLabels('Very Difficult', 'Very Easy')
    .setRequired(true);

  form.addScaleItem()
    .setTitle('How would you rate the website\'s user interface and navigation?')
    .setBounds(1, 5)
    .setLabels('Poor', 'Excellent')
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('How do you typically find challenges to attempt? (Select all that apply)')
    .setChoiceValues([
      'Browse the newest challenges',
      'Filter by difficulty level',
      'Filter by platform (Windows, Linux, etc.)',
      'Search by name or author',
      'Random selection',
      'Recommendations from others',
      'Work through challenges by a specific author'
    ])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Have you submitted any challenges to crackmes.one?')
    .setChoiceValues([
      'Yes, multiple challenges',
      'Yes, one challenge',
      'No, but I plan to',
      'No, and I don\'t plan to'
    ])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Have you submitted any writeups (solutions) to crackmes.one?')
    .setChoiceValues([
      'Yes, multiple writeups',
      'Yes, one writeup',
      'No, but I plan to',
      'No, and I don\'t plan to'
    ])
    .setRequired(false);

  // ============================================
  // SECTION 3: Challenge Preferences
  // ============================================
  form.addPageBreakItem()
    .setTitle('Challenge Preferences')
    .setHelpText('Help us understand what types of challenges you enjoy.');

  form.addCheckboxItem()
    .setTitle('Which platforms do you prefer for crackmes? (Select all that apply)')
    .setChoiceValues([
      'Windows (PE/x86/x64)',
      'Linux (ELF)',
      'macOS',
      'Android (APK)',
      'iOS',
      'Web-based',
      'Multi-platform'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Which difficulty levels do you typically attempt? (Select all that apply)')
    .setChoiceValues([
      '1 - Very Easy',
      '2 - Easy',
      '3 - Medium',
      '4 - Hard',
      '5 - Very Hard',
      '6 - Insane'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('What types of protections/techniques interest you most? (Select all that apply)')
    .setChoiceValues([
      'Serial/keygen challenges',
      'Anti-debugging techniques',
      'Obfuscation/packing',
      'Cryptography-based',
      'Algorithm reversing',
      'Network/protocol analysis',
      'Virtual machine-based protection',
      '.NET/Java reversing',
      'Malware analysis style'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Which tools do you primarily use? (Select all that apply)')
    .setChoiceValues([
      'IDA Pro',
      'Ghidra',
      'x64dbg / x32dbg',
      'Binary Ninja',
      'Radare2 / Cutter',
      'GDB',
      'dnSpy / ILSpy (.NET)',
      'JADX (Android)',
      'Frida',
      'Other'
    ])
    .setRequired(false);

  // ============================================
  // SECTION 4: Features & Improvements
  // ============================================
  form.addPageBreakItem()
    .setTitle('Features & Improvements')
    .setHelpText('Share your ideas for making crackmes.one better.');

  form.addCheckboxItem()
    .setTitle('Which new features would you most like to see? (Select up to 5)')
    .setChoiceValues([
      'Achievement/badge system',
      'Leaderboards',
      'Challenge series/learning paths',
      'Bookmark/favorites system',
      'Automated solution verification system',
      'Technique tagging system (e.g., tags like "encrypted strings", "control flow obfuscation", "anti-debugging" to help filter challenges by protection techniques used)',
      'Community blog for writeups and tutorials',
      'Other'
    ])
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What do you like most about crackmes.one?')
    .setHelpText('What keeps you coming back?')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('What frustrates you most about crackmes.one?')
    .setHelpText('What could be improved?')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('Do you have any other suggestions or feedback?')
    .setHelpText('Feel free to share any additional thoughts.')
    .setRequired(false);

  // ============================================
  // SECTION 5: Community Engagement (Optional)
  // ============================================
  form.addPageBreakItem()
    .setTitle('Stay Connected (Optional)')
    .setHelpText('Help us follow up on your feedback.');

  form.addMultipleChoiceItem()
    .setTitle('Would you be interested in participating in future surveys or beta testing?')
    .setChoiceValues([
      'Yes',
      'No',
      'Maybe'
    ])
    .setRequired(false);

  form.addTextItem()
    .setTitle('If you\'d like us to follow up, please provide your email (optional)')
    .setHelpText('Your email will only be used for survey follow-up.')
    .setRequired(false);

  // Log the form URL
  Logger.log('Form created successfully!');
  Logger.log('Form URL: ' + form.getPublishedUrl());
  Logger.log('Edit URL: ' + form.getEditUrl());

  // Return the form for reference
  return form;
}
