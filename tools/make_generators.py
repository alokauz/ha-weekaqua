"""Build dashboard/make-card*.jinja from the cards (run after changing a card)."""
from pathlib import Path

PREFIX = "b3_0_l600pro_71"
HEAD = (
    "{#- Week Aqua: prints your dashboard card with your own entity IDs.\n"
    "    Developer tools -> Template: replace everything there with this file,\n"
    "    then copy the result on the right into a new card (Add card -> Manual). -#}\n"
    "{%- set p = (integration_entities('weekaqua') | select('match', 'light[.]') | first | default('light.none'))[6:] -%}\n"
)
for name in ("weekaqua-card", "weekaqua-card.ru", "weekaqua-chart", "weekaqua-chart.ru"):
    card = Path(f"dashboard/{name}.yaml").read_text()
    body = "{% raw %}" + card.replace(PREFIX, "{% endraw %}{{ p }}{% raw %}") + "{% endraw %}"
    Path(f"dashboard/make-{name.replace('weekaqua-', '')}.jinja").write_text(HEAD + body)
    print("wrote", f"dashboard/make-{name.replace('weekaqua-', '')}.jinja")
