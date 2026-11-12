def count_vowels(text):
    """Count the vowels a, e, i, o, u in text, ignoring letter case."""
    return sum(1 for ch in text if ch in 'aeio')
