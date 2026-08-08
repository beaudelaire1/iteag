"""Non-régressions du rendu public de la candidature."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_honeypot_est_present_sans_libelle_visible(client):
    reponse = client.get(reverse("admissions:candidature_form"))

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'name="honeypot"' in html
    assert 'type="hidden"' in html
    assert 'for="id_honeypot"' not in html
