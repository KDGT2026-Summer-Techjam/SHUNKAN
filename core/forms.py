from typing import ClassVar, cast

from django import forms
from django.utils import timezone

from .models import Category, MomentLog, Photo, Room, Task
from .room_state import log_post_permission


def _task_label(task: Task) -> str:
    if task.due_date:
        return f"{task.title}（{task.due_date:%m/%d}まで）"
    return f"{task.title}（期限なし）"


class TaskChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Task) -> str:
        return _task_label(obj)


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

    def __init__(self, *args, room, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room

    def clean_due_date(self):
        due_date = self.cleaned_data["due_date"]
        if due_date:
            starts_on = timezone.localtime(self.room.starts_at).date()
            ends_on = timezone.localtime(self.room.ends_at).date()
            if not starts_on <= due_date <= ends_on:
                raise forms.ValidationError("期限はRoom期間内で設定してください。")
        return due_date


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


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields: ClassVar[list[str]] = ["name", "color"]
        labels: ClassVar[dict[str, str]] = {
            "name": "カテゴリ名",
            "color": "カラー",
        }
        widgets: ClassVar[dict[str, object]] = {
            "name": forms.TextInput(
                attrs={"class": "field__input", "placeholder": "例：花火"}
            ),
            "color": forms.TextInput(attrs={"class": "field__input", "type": "color"}),
        }


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
    entry_type = forms.ChoiceField(
        choices=MomentLog.EntryType.choices,
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = MomentLog
        fields: ClassVar[list[str]] = ["body", "category", "task", "entry_type"]
        widgets: ClassVar[dict[str, object]] = {
            "body": forms.Textarea(attrs={"class": "field__textarea"}),
            "category": forms.Select(attrs={"class": "field__input"}),
            "task": forms.Select(attrs={"class": "field__input"}),
        }

    def __init__(self, *args, room, now=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.room = room
        # ModelFormのモデル検証で、Task/Categoryの所属Roomを正しく判定できるようにする。
        self.instance.room = room
        self.now = now
        self.permission = None
        category_field = cast(forms.ModelChoiceField, self.fields["category"])
        category_field.queryset = room.categories.all()
        self.fields["task"] = TaskChoiceField(
            queryset=room.tasks.all(),
            required=False,
            label="関連タスク",
            widget=forms.Select(attrs={"class": "field__input"}),
        )

    def clean_entry_type(self):
        return self.cleaned_data.get("entry_type") or MomentLog.EntryType.MOMENT

    def clean(self):
        cleaned_data = super().clean()
        entry_type = cleaned_data.get("entry_type") or MomentLog.EntryType.MOMENT
        self.permission = log_post_permission(self.room, entry_type, now=self.now)
        if not self.permission.allowed:
            raise forms.ValidationError(self.permission.message)
        return cleaned_data
