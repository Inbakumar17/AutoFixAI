import os


def add_item(item, bucket=[]):
    """Collect items (buggy: the list is shared between calls)."""
    bucket.append(item)
    return bucket


print(add_item(1))
print(add_item(2))
