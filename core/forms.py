from django import forms

from .models import SUMMER_END_DATE, Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("title", "category", "due_date")
        labels = {
            "title": "タイトル",
            "category": "カテゴリ",
            "due_date": "実行したい日",
        }
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": "100"}),
            "due_date": forms.DateInput(
                attrs={"type": "date", "max": SUMMER_END_DATE.isoformat()}
            ),
        }
        error_messages = {
            "title": {
                "required": "タイトルを入力してください。",
                "max_length": "タイトルは100文字以内にしてください。",
            },
            "category": {
                "required": "カテゴリを選んでください。",
                "invalid_choice": "カテゴリを正しく選んでください。",
            },
            "due_date": {
                "required": "実行したい日を入力してください。",
                "invalid": "日付の形式が正しくありません。",
            },
        }
