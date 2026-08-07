import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def grouper_pieces_existantes(apps, schema_editor):
    Piece = apps.get_model("admissions", "PieceDemandee")
    Demande = apps.get_model("admissions", "DemandePieces")

    dossiers = Piece.objects.filter(demande__isnull=True).values_list("dossier_id", flat=True).distinct()
    for dossier_id in dossiers:
        pieces = list(Piece.objects.filter(dossier_id=dossier_id, demande__isnull=True))
        if not pieces:
            continue

        statuts = {piece.statut for piece in pieces}
        if "deposee" in statuts:
            statut = "a_verifier"
        elif "refusee" in statuts:
            statut = "a_corriger"
        elif statuts == {"validee"}:
            statut = "validee"
        else:
            statut = "a_fournir"

        dates = [piece.date_limite for piece in pieces if piece.date_limite]
        demande = Demande.objects.create(
            dossier_id=dossier_id,
            message="",
            date_limite=min(dates) if dates else None,
            statut=statut,
            demandee_par_id=next((piece.demandee_par_id for piece in pieces if piece.demandee_par_id), None),
            date_soumission=max((piece.date_depot for piece in pieces if piece.date_depot), default=None),
            date_decision=max((piece.date_decision for piece in pieces if piece.date_decision), default=None),
        )
        Piece.objects.filter(pk__in=[piece.pk for piece in pieces]).update(demande_id=demande.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0004_supprimer_piececomplementaire"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DemandePieces",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("message", models.TextField(blank=True, verbose_name="Message commun au candidat")),
                ("date_limite", models.DateField(blank=True, null=True, verbose_name="À fournir avant le")),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("a_fournir", "À fournir"),
                            ("a_verifier", "Déposée — à vérifier"),
                            ("a_corriger", "À corriger"),
                            ("validee", "Validée"),
                        ],
                        default="a_fournir",
                        max_length=20,
                    ),
                ),
                ("date_soumission", models.DateTimeField(blank=True, null=True, verbose_name="Déposée le")),
                ("date_decision", models.DateTimeField(blank=True, null=True, verbose_name="Traitée le")),
                (
                    "demandee_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="demandes_pieces_creees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dossier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="demandes_pieces",
                        to="admissions.dossiercandidature",
                    ),
                ),
            ],
            options={
                "verbose_name": "Demande de pièces",
                "verbose_name_plural": "Demandes de pièces",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="piecedemandee",
            name="demande",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pieces",
                to="admissions.demandepieces",
            ),
        ),
        migrations.RunPython(grouper_pieces_existantes, migrations.RunPython.noop),
    ]
