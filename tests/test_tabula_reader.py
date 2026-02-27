from oemof.thermal_building_model.tabula.tabula_reader import Building

def test_tabula_reader():
    number_of_time_steps = 100
    # Generates 5RC Building-Model
    generic_building_example = Building(
        country="DE",
        construction_year=1980,
        floor_area=200,
        class_building="average",
        building_type="SFH",
        refurbishment_status="no_refurbishment",
        number_of_time_steps=number_of_time_steps,
    )
    specific_building_example = Building(
        tabula_building_code="DE.N.SFH.05.Gen.ReEx.001.002",
        class_building="average",
        number_of_time_steps=number_of_time_steps,
    )
    generic_building_example.calculate_all_parameters()
    specific_building_example.calculate_all_parameters()

    assert generic_building_example.a_floor["a_floor_1"] == 77.36549165120594
    assert specific_building_example.a_floor["a_floor_1"] == 115.8
    assert generic_building_example.h_tr_em == 235.54147125751112
    assert specific_building_example.h_tr_em == 169.44835342102402
    assert generic_building_example.h_transmission == 337.832305942905
    assert specific_building_example.h_transmission == 204.67835342102404
