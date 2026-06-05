import quiet


def _quiet(args: str) -> str:
    quiet.set_manual_quiet(True)
    return "🔇 Quiet mode ON\nNotifications will be queued\n/loud to resume"


def _loud(args: str) -> str:
    quiet.set_manual_quiet(False)
    items = quiet.flush_queue()
    if items:
        summary = quiet.build_summary(items)
        return f"🔊 Notifications resumed\n\n{summary}"
    return "🔊 Notifications resumed\nNo queued items"


HANDLERS = {
    "/quiet": _quiet,
    "/loud": _loud,
}