from typing import ClassVar, cast

from django import forms
from django.utils import timezone

from .models import MomentLog, Photo, Room, Task


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields: ClassVar[list[str]] = ["name", "starts_at", "ends_at"]
        labels: ClassVar[dict[str, str]] = {
            "name": "Room名",
            "starts_at": "開始日時",
            "ends_at": "終了日時",
        }
        widgets: ClassVar[dict[str, object]] = {
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


class TaskUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("title", "due_date")
        labels = {"title": "タイトル", "due_date": "期限"}
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class MomentLogUpdateForm(forms.ModelForm):
    class Meta:
        model = MomentLog
        fields = ("body",)
        labels = {"body": "SHUNKAN-log本文"}


class PhotoUpdateForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ("caption",)
        labels = {"caption": "写真へのひとこと"}


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields: ClassVar[list[str]] = ["title", "due_date", "category"]
        widgets: ClassVar[dict[str, object]] = {
            "title": forms.TextInput(attrs={"class": "field__input"}),
            "due_date": forms.DateInput(
                attrs={"class": "field__input", "type": "date"},
            ),
            "category": forms.Select(attrs={"class": "field__input"}),
        }

    def __init__(self, *args, room, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room
        category_field = cast(forms.ModelChoiceField, self.fields["category"])
        category_field.queryset = room.categories.all()

    def clean_due_date(self):
        due_date = self.cleaned_data["due_date"]
        if due_date:
            starts_on = timezone.localtime(self.room.starts_at).date()
            ends_on = timezone.localtime(self.room.ends_at).date()
            if not starts_on <= due_date <= ends_on:
                raise forms.ValidationError("期限はRoom期間内で設定してください。")
        return due_date


class MomentLogForm(forms.ModelForm):
    class Meta:
        model = MomentLog
        fields: ClassVar[list[str]] = ["body", "occurred_at", "category", "task"]
        widgets: ClassVar[dict[str, object]] = {
            "body": forms.Textarea(attrs={"class": "field__textarea"}),
            "occurred_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": "field__input", "type": "datetime-local"},
            ),
            "category": forms.Select(attrs={"class": "field__input"}),
            "task": forms.Select(attrs={"class": "field__input"}),
        }

    def __init__(self, *args, room, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room
        category_field = cast(forms.ModelChoiceField, self.fields["category"])
        task_field = cast(forms.ModelChoiceField, self.fields["task"])
        category_field.queryset = room.categories.all()
        task_field.queryset = room.tasks.all()

    def clean_occurred_at(self):
        occurred_at = self.cleaned_data["occurred_at"]
        if not self.room.starts_at <= occurred_at <= self.room.ends_at:
            raise forms.ValidationError("発生日時はRoom期間内で設定してください。")
        return occurred_at
