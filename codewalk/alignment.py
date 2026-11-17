"""Publication checks for dataset identity, paper provenance and construction contracts."""

REQUIRED_AXES=('hugging_face_identity','paper_identity_and_results','composition_methods')


def failures(report):
    reasons=[]
    for domain,item in report['datasets'].items():
        for axis in REQUIRED_AXES:
            if item.get(axis) is not True:
                reasons.append(f'{domain}: {axis} is not verified')
    if set(report['datasets'])!={'bugfixing','verus','bigo','codeclone'}:
        reasons.append('All four domains must be audited')
    return reasons


def require_alignment(report):
    issues=failures(report)
    if issues:raise ValueError('Three-way alignment failed:\n'+'\n'.join(issues))
