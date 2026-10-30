"""Canonical WBS template for an individual residential construction project.

Only structure is created: zero fictitious budget, expenses, commitments, dates
or financial postings. All phases are initially PLANNING and user-editable.
"""

RESIDENTIAL_WBS_PHASES: tuple[tuple[str, str], ...] = (
    ("01", "Planificación e inversión inicial"),
    ("02", "Terreno, documentación y estudios"),
    ("03", "Diseño arquitectónico y planos de ingeniería"),
    ("04", "Presupuesto, permisos y licencias"),
    ("05", "Preparación y nivelación del terreno"),
    ("06", "Excavaciones y cimentaciones"),
    ("07", "Columnas, vigas, losas y estructura"),
    ("08", "Mampostería, paredes y cubierta de techo"),
    ("09", "Instalaciones eléctricas e hidrosanitarias"),
    ("10", "Repellos, pisos, cerámica, cielo falso y pintura"),
    ("11", "Puertas, ventanas, muebles y equipamiento"),
    ("12", "Obras exteriores, drenajes, muros y jardines"),
    ("13", "Inspecciones, correcciones y entrega final"),
)
