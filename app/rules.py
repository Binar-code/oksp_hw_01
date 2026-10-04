import hashlib
import hmac
import secrets


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f'{salt}:{digest.hex()}'


def check_password(password, saved):
    return hmac.compare_digest(hash_password(password, saved.split(':')[0]), saved)


def can_change_status(current, target):
    if current == 'new' and target == 'in_progress':
        return True
    if current == 'in_progress' and target == 'closed':
        return True
    return False


def reaction(created_at, first_reply_at, response_minutes, now):
    end = now
    if first_reply_at is not None:
        end = first_reply_at
    minutes = (end - created_at).total_seconds() / 60
    reaction_minutes = None
    if first_reply_at is not None:
        reaction_minutes = round(minutes, 2)
    return {'reaction_minutes': reaction_minutes, 'overdue': minutes > response_minutes}
