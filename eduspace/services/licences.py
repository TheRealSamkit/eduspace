"""
Plain-language licence registry for EduSpace public uploads.

Provides a single source of truth for licence keys, student-friendly labels,
plain-language summaries, selection guidance, and copyright cautions.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LicenceInfo:
    """Metadata describing a sharing licence option."""

    key: str
    label: str
    plain_summary: str
    choose_when: str
    caution: str


LICENCES = [
    LicenceInfo(
        key="own_work",
        label="My own work (I made this)",
        plain_summary=(
            "You created it yourself. Other EduSpace users can download and study from it; "
            "you keep ownership."
        ),
        choose_when="You wrote these notes, summaries, or solutions yourself.",
        caution="Do not pick this if you copied textbook pages or teacher slides.",
    ),
    LicenceInfo(
        key="cc_by",
        label="Free to reuse if credited to me (CC BY 4.0)",
        plain_summary=(
            "Anyone can share or adapt your work, even commercially, as long as they credit you."
        ),
        choose_when="You want your work widely reusable with credit.",
        caution="You cannot revoke this permission later once shared.",
    ),
    LicenceInfo(
        key="cc_by_sa",
        label="Free to reuse, remixes share alike (CC BY-SA 4.0)",
        plain_summary=(
            "Anyone can share or build on your work with credit, and any remixes must use the same licence."
        ),
        choose_when="You want improvements to stay open under the same terms.",
        caution="Remixes must carry this exact licence.",
    ),
    LicenceInfo(
        key="cc0",
        label="Free for anyone, no credit needed (CC0)",
        plain_summary=(
            "You give up all copyright claims so anyone can use, edit, or share it freely "
            "without crediting you."
        ),
        choose_when="You want zero restrictions and no credit requirement.",
        caution="Permanent: you waive copyright worldwide.",
    ),
    LicenceInfo(
        key="public_domain",
        label="Public domain (copyright expired or never applied)",
        plain_summary=(
            "This material has no copyright restrictions because copyright expired or never applied."
        ),
        choose_when="The work is an older classic, government document, or already in the public domain.",
        caution="Verify that copyright truly expired or never applied.",
    ),
]

LICENCES_BY_KEY = {lic.key: lic for lic in LICENCES}

LICENCE_CHOICES = [(lic.key, lic.label) for lic in LICENCES]

LICENCE_WARNING = (
    "Notes copied from a textbook, teacher slides, or another student's notes are not yours "
    "to share publicly unless they are openly licensed."
)


def get_licence(key):
    """Return LicenceInfo for the given database key, or None if unknown."""
    return LICENCES_BY_KEY.get(key)
