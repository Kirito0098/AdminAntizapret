def register_current_user_context_processor(app, session_obj, user_model):
    @app.context_processor
    def inject_current_user():
        user = None
        if "username" in session_obj:
            user = user_model.query.filter_by(username=session_obj["username"]).first()
        return {"current_user": user}
