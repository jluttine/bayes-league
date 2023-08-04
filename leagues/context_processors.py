def logins(request):
    print("In cont.proc.", dict(**request.session))
    return {
        "logins": request.session.get("logins", []),
    }
