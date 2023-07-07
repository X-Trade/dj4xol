from django import forms


class NewGameForm(forms.Form):
    your_name = forms.CharField(label="Your name", max_length=100)

class JoinGameForm(forms.Form):
    your_name = forms.CharField(label="Your name", max_length=100)