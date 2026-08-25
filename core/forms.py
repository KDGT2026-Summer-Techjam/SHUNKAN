from django import forms

from .models import Room


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "starts_at", "ends_at"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "field__input", "placeholder": "例：文化祭まで"},
            ),
            "starts_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": "field__input", "type": "datetime-local"},
            ),
            "ends_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": "field__input", "type": "datetime-local"},
            ),
        }
