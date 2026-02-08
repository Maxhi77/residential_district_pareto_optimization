def get_resident_range(household_dicts):
    ranges = {}
    for key, household_group in household_dicts.items():
        values = list(household_group.values())
        ranges[key] = (min(values), max(values))
    return ranges

sobol_households = {
    "CHR07 Single with work": 1,
"CHR33 Couple under 30 years with work": 2,
    "CHR03 Family, 1 child, both at work": 3,
    "CHR27 Family both at work, 2 children": 4,
    "CHR05 Family, 3 children, both with work": 5,
    "CHR15 Multigenerational Home: working couple, 2 children, 2 seniors": 6,

}

households_with_families = {
    "CHR03 Family, 1 child, both at work": 3,
    "CHR22 Single woman, 1 child, with work": 2,
    "CHR43 Single man with 1 child, with work": 2,
    "CHR45 Family with 1 child, 1 at work, 1 at home": 3,
    #"CHR61 Family, 1 child, both at work, early living pattern": 3,
    "CHR27 Family both at work, 2 children": 4,
    "CHR44 Family with 2 children, 1 at work, 1 at home": 4,
    "CHR53 2 Parents, 1 Working, 2 Children": 4,
    "CHR05 Family, 3 children, both with work": 5,
    "CHR20 one at work, one work home, 3 children": 5,
   # "CHR41 Family with 3 children, both at work": 5,
    "CHR15 Multigenerational Home: working couple, 2 children, 2 seniors": 6,

}


households_with_seniors = {
    "CHR14 3 adults: Couple, 30- 64 years, both at work + Senior at home": 3,
    "CHR30 Single, Retired Man": 1,
    "CHR31 Single, Retired Woman": 1,
    "CHR54 Retired Couple, no work": 2,
}

households_adult_only = {
    "CHR02 Couple, 30 - 64 age, with work": 2,
    "CHR07 Single with work": 1,
    "CHR11 Student, Female, Philosophy": 1,
    "CHR13 Student with Work": 1,
    "CHR33 Couple under 30 years with work": 2,
    "CHR34 Couple under 30 years, one at work, one at home": 2,
    "CHR52 Student Flatsharing": 3,
    "CHR19 Couple, 30 - 64 years, both at work, with homehelp": 3

}

def classify_household(residents, share_under_18, share_over_65):
    # Anteile zu Personen umrechnen
    n_children = round((share_under_18 / 100) * residents)
    n_seniors = round((share_over_65 / 100) * residents)

    # Nachregelung, falls zu viele
    while n_children + n_seniors > residents:
        if n_children > n_seniors:
            n_children -= 1
        elif n_seniors > 0:
            n_seniors -= 1
        else:
            break

    n_adults = residents - n_children - n_seniors

    return {
        'residents': residents,
        'children': n_children,
        'seniors': n_seniors,
        'adults': n_adults
    }
