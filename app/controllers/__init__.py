"""Controllers package for crackmes.one"""

from flask import Blueprint


def register_blueprints(app):
    """Register all controller blueprints."""
    from app.controllers.index import index_bp
    from app.controllers.login import login_bp
    from app.controllers.register import register_bp
    from app.controllers.user import user_bp
    from app.controllers.crackme import crackme_bp
    from app.controllers.solution import solution_bp
    from app.controllers.comment import comment_bp
    from app.controllers.search import search_bp
    from app.controllers.faq import faq_bp
    from app.controllers.notifications import notifications_bp
    from app.controllers.rss import rss_bp
    from app.controllers.rating import rating_bp
    from app.controllers.rules import rules_bp
    from app.controllers.password import password_bp
    from app.controllers.password_reset import password_reset_bp
    from app.controllers.static import static_bp
    from app.controllers.error import error_bp
    from app.controllers.sub import sub_bp

    app.register_blueprint(index_bp)
    app.register_blueprint(login_bp)
    app.register_blueprint(register_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(crackme_bp)
    app.register_blueprint(solution_bp)
    app.register_blueprint(comment_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(faq_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(rss_bp)
    app.register_blueprint(rating_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(password_bp)
    app.register_blueprint(password_reset_bp)
    app.register_blueprint(static_bp)
    app.register_blueprint(error_bp)
    app.register_blueprint(sub_bp)