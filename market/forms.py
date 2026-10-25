from django.contrib.auth.models import User
from django import forms

from market.models import Listing


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = ["title", "description", "price", "category", "seller_note"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        # Permission flags must only be changed by trusted administrators.
        fields = ["first_name", "last_name", "email"]
