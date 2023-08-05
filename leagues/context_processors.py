def logins(request):
    return {
        "logins": request.session.get("logins", []),
    }
