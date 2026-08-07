# ruff: noqa: I001
from django.db import migrations


STATUT_DEMANDE_PAR_STATUT_PIECE = {
    "demandee": "a_fournir",
    "deposee": "a_verifier",
    "refusee": "a_corriger",
    "validee": "validee",
}


def separer_lots_herites(apps, schema_editor):
    DemandePieces = apps.get_model("admissions", "DemandePieces")
    PieceDemandee = apps.get_model("admissions", "PieceDemandee")

    for demande in DemandePieces.objects.all().iterator():
        pieces = list(PieceDemandee.objects.filter(demande_id=demande.pk).order_by("pk"))
        groupes = {}
        for piece in pieces:
            statut_demande = STATUT_DEMANDE_PAR_STATUT_PIECE.get(piece.statut, "a_fournir")
            groupes.setdefault(statut_demande, []).append(piece)

        if len(groupes) <= 1:
            if groupes:
                statut_unique = next(iter(groupes))
                if demande.statut != statut_unique:
                    demande.statut = statut_unique
                    demande.save(update_fields=["statut"])
            continue

        premier = True
        for statut, pieces_du_groupe in groupes.items():
            if premier:
                cible = demande
                cible.statut = statut
                cible.date_soumission = max(
                    (piece.date_depot for piece in pieces_du_groupe if piece.date_depot),
                    default=None,
                )
                cible.date_decision = max(
                    (piece.date_decision for piece in pieces_du_groupe if piece.date_decision),
                    default=None,
                )
                cible.save(update_fields=["statut", "date_soumission", "date_decision"])
                premier = False
            else:
                cible = DemandePieces.objects.create(
                    dossier_id=demande.dossier_id,
                    message=demande.message,
                    date_limite=demande.date_limite,
                    statut=statut,
                    demandee_par_id=demande.demandee_par_id,
                    date_soumission=max(
                        (piece.date_depot for piece in pieces_du_groupe if piece.date_depot),
                        default=None,
                    ),
                    date_decision=max(
                        (piece.date_decision for piece in pieces_du_groupe if piece.date_decision),
                        default=None,
                    ),
                )

            PieceDemandee.objects.filter(pk__in=[piece.pk for piece in pieces_du_groupe]).update(
                demande_id=cible.pk
            )


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0005_demandepieces_groupee"),
    ]

    operations = [
        migrations.RunPython(separer_lots_herites, migrations.RunPython.noop),
    ]
