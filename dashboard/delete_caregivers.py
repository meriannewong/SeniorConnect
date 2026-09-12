import app as sc

OLD_USERNAMES = [f"caregiver{i:03d}" for i in range(2, 9)]  # caregiver002 .. caregiver008

for username in OLD_USERNAMES:
    if sc.get_user(username) is None:
        print(f"{username} doesn't exist, skipping")
        continue

    for med in sc.get_medications(username):
        sc.delete_medication(username, med["id"])
    for alert in sc.get_alerts(username, active_only=False):
        sc.delete_alert(username, alert["id"])
    sc.delete_user(username)
    print(f"deleted {username} and all its data")

print("done")