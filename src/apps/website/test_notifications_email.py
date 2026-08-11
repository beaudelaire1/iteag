"""Tests des deux courriels émis par le formulaire de contact."""

from types import SimpleNamespace

import pytest
from django import forms
from django.core import mail

from apps.website.models import ContactPage


@pytest.mark.django_db
def test_un_message_de_contact_previent_le_secretariat_et_le_visiteur():
    page = ContactPage(destinataire="secretariat@example.org")
    formulaire = SimpleNamespace(
        cleaned_data={
            "nom": "Visiteur test",
            "adresse_email": "visiteur@example.org",
            "message": "Bonjour",
            "honeypot": "",
        },
        fields={"adresse_email": forms.EmailField()},
    )

    page._send_notification_email(formulaire)
    page._send_confirmation_email(formulaire)

    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == ["secretariat@example.org"]
    assert "Visiteur test" in mail.outbox[0].body
    assert mail.outbox[0].alternatives
    assert mail.outbox[1].to == ["visiteur@example.org"]
    assert "bien reçu votre message" in mail.outbox[1].body
    assert mail.outbox[1].alternatives
