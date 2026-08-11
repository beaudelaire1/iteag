"""Tests des deux courriels émis par le formulaire de contact."""

from types import SimpleNamespace

import pytest
from django import forms
from django.core import mail

from apps.accounts.models import User
from apps.website.models import ContactPage


@pytest.mark.django_db
def test_un_message_de_contact_previent_admin_secretariat_et_visiteur():
    User.objects.create_user(
        username="admin-contact",
        email="admin@example.org",
        role=User.Role.ADMIN,
    )
    User.objects.create_user(
        username="secretariat-contact",
        email="secretariat@example.org",
        role=User.Role.SECRETARIAT,
    )
    User.objects.create_user(
        username="secretariat-inactif",
        email="inactif@example.org",
        role=User.Role.SECRETARIAT,
        is_active=False,
    )
    User.objects.create_user(
        username="etudiant-contact",
        email="etudiant@example.org",
        role=User.Role.ETUDIANT,
    )
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

    assert len(mail.outbox) == 3
    notifications = mail.outbox[:2]
    assert {message.to[0] for message in notifications} == {
        "admin@example.org",
        "secretariat@example.org",
    }
    assert all("Visiteur test" in message.body for message in notifications)
    assert all(message.alternatives for message in notifications)
    assert mail.outbox[2].to == ["visiteur@example.org"]
    assert "bien reçu votre message" in mail.outbox[2].body
    assert mail.outbox[2].alternatives
