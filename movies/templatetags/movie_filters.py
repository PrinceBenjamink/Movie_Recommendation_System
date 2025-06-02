from django import template
from django.utils.translation import get_language_info

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiplies the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def language_name(lang_code):
    """Converts a language code to its full name"""
    if not lang_code:
        return "Unknown"
    
    try:
        return get_language_info(lang_code)['name']
    except KeyError:
        # Fallback for language codes not recognized by Django
        language_mapping = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'ja': 'Japanese',
            'ko': 'Korean',
            'zh': 'Chinese',
            'hi': 'Hindi',
            'ru': 'Russian',
            'pt': 'Portuguese',
            'ta': 'Tamil',
            'te': 'Telugu',
            'ml': 'Malayalam',
            'bn': 'Bengali',
            # Add more languages as needed
        }
        return language_mapping.get(lang_code, f"Unknown ({lang_code})")
