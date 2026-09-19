#!/usr/bin/env python3
"""Genera documentos de ejemplo para probar la clasificacion sin datos reales.

    python scripts/documentos_demo.py --salida data/documentos/entrada

Crea PDFs cortos con el lenguaje tipico de cada categoria (demanda, citacion,
mocion, orden, reclamacion, reporte policial, expediente medico, poliza,
factura, contrato, declaracion y correspondencia) para un mismo expediente,
de modo que tambien se vea la agrupacion por caso.
"""
from __future__ import annotations

import argparse
from pathlib import Path

CASO = "3:24-cv-05148-MGL"
ACTORA = "Dona M. Fry"
DEMANDADA = "United States of America"

DOCUMENTOS = [
    ("summons.pdf", f"""UNITED STATES DISTRICT COURT
DISTRICT OF SOUTH CAROLINA
Case No. {CASO}     Date Filed 09/20/24
SUMMONS IN A CIVIL ACTION
To: {DEMANDADA}
You are hereby summoned and required to serve upon plaintiff's attorney an answer
to the complaint which is herewith served upon you, within 21 days after service.
Proof of service shall be filed with the Clerk of Court."""),

    ("motion_extend.pdf", f"""UNITED STATES DISTRICT COURT
DISTRICT OF SOUTH CAROLINA
Case No. {CASO}     Date Filed 10/04/24
MOTION FOR EXTENSION OF TIME
Defendant respectfully moves this Court for an extension of time to file its answer.
MEMORANDUM IN SUPPORT: counsel requires additional time to review medical records.
Movant certifies that opposing counsel does not oppose this motion."""),

    ("order_granting.pdf", f"""UNITED STATES DISTRICT COURT
DISTRICT OF SOUTH CAROLINA
Case No. {CASO}     Date Filed 10/11/24
ORDER GRANTING MOTION FOR EXTENSION OF TIME
Upon review of the motion, the Court finds good cause shown.
IT IS SO ORDERED.
s/ Mary Geiger Lewis, United States District Judge"""),

    ("form95_claim.pdf", f"""STANDARD FORM 95
CLAIM FOR DAMAGE, INJURY, OR DEATH
Submitted under the Federal Tort Claims Act
Date of incident: 01/15/2023      Date submitted: 02/08/2024
Claimant: {ACTORA}
Agency: United States Postal Service
Amount of claim: $265,271.00
Basis of claim: motor vehicle collision caused by a USPS employee."""),

    ("police_report.pdf", f"""SOUTH CAROLINA TRAFFIC COLLISION REPORT
Incident report number TC-2023-004512     Date: 01/15/2023
Location: Park Road and Dupre Mill Road, Lexington County
Unit 1 driver: {ACTORA}, 2015 Acura
Unit 2 driver: Michelle Moni Livingston, USPS vehicle
Investigating officer: Cpl. R. Daniels
Contributing factor: disregarded stop sign."""),

    ("medical_record.pdf", """LEXINGTON MEDICAL CENTER
MEDICAL RECORD - EMERGENCY DEPARTMENT
Patient name: Dona M. Fry       Date of birth: 03/22/1965
Date of service: 01/15/2023
Chief complaint: neck and back pain following motor vehicle collision.
Diagnosis: cervical strain, lumbar strain (ICD-10 S13.4XXA, S39.012A).
Treatment plan: physical therapy three times weekly, MRI of cervical spine.
Attending physician: Dr. A. Patel, MD"""),

    ("medical_bill.pdf", """LEXINGTON MEDICAL CENTER - BILLING DEPARTMENT
INVOICE
Invoice No. LMC-884120      Date: 02/02/2023
Bill to: Dona M. Fry
Description: emergency department services, radiology, physical therapy
Subtotal: $8,430.00
Amount due: $8,430.00
Payment terms: net 30 days."""),

    ("insurance_letter.pdf", """STATE MUTUAL INSURANCE COMPANY
Claims Department
Date: 03/05/2024
Policy number SM-4471902     Claim No. 2024-118834
Dear Ms. Fry,
This letter acknowledges receipt of your claim. Our claims adjuster has been
assigned to evaluate coverage limits under the declaration page of your policy.
Sincerely,
J. Alvarez, Claims Adjuster"""),

    ("settlement_agreement.pdf", f"""SETTLEMENT AGREEMENT AND RELEASE OF ALL CLAIMS
This Agreement is entered into between {ACTORA} and {DEMANDADA}.
WHEREAS the parties wish to resolve all disputes arising from the collision of
January 15, 2023, and WHEREAS no admission of liability is made,
NOW THEREFORE the parties agree to the terms set forth herein.
IN WITNESS WHEREOF the parties have executed this Agreement on 11/15/2024."""),

    ("affidavit.pdf", f"""AFFIDAVIT OF WITNESS
Case No. {CASO}
STATE OF SOUTH CAROLINA, COUNTY OF LEXINGTON
Personally appeared before me the undersigned witness, being duly sworn,
who states under penalty of perjury that he observed the collision on
January 15, 2023 at the intersection of Park Road and Dupre Mill Road.
Sworn statement given this 05/20/2024."""),

    ("letter_counsel.pdf", f"""McWHIRTER, BELLINGER & ASSOCIATES, P.A.
2437 Mineral Springs Road, Lexington, South Carolina 29072
Date: 04/18/2024
RE: {ACTORA} v. {DEMANDADA} - Case No. {CASO}
Dear Counsel,
Enclosed please find the medical records and billing statements requested in
your discovery letter. Please contact our office with any questions.
Sincerely,
Christopher M. Cunningham, Esquire"""),

    ("notice_appearance.pdf", f"""UNITED STATES DISTRICT COURT
DISTRICT OF SOUTH CAROLINA
Case No. {CASO}     Date Filed 09/25/24
NOTICE OF APPEARANCE
Please take notice that the undersigned appears as counsel of record.
CERTIFICATE OF SERVICE
I hereby certify that a copy of the foregoing was served upon all counsel."""),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera documentos de ejemplo")
    ap.add_argument("--salida", default="data/documentos/entrada")
    args = ap.parse_args()
    import pymupdf

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, cuerpo in DOCUMENTOS:
        doc = pymupdf.open()
        pagina = doc.new_page()
        pagina.insert_textbox(pymupdf.Rect(60, 60, 540, 760), cuerpo,
                              fontsize=11, fontname="helv", align=0)
        doc.save(str(destino / nombre))
        doc.close()
    print(f"{len(DOCUMENTOS)} documentos de ejemplo en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
