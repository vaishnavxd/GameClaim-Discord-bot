from datetime import timedelta

def format_duration(delta):
    parts = []
    if delta.days > 0:
        parts.append(f"{delta.days} day{'s' if delta.days != 1 else ''}")
    hours = delta.seconds // 3600
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    minutes = (delta.seconds % 3600) // 60
    if minutes > 0 and delta.days == 0:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    return " ".join(parts) if parts else "Ends soon!"
