"""Relief maps of two installs side by side (JNSQ and stock): each body gets the map of its radius in the game flown."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import service


def write_map(folder, body, radius):
    file = service.map_file(body, radius)
    open(os.path.join(folder, file), 'wb').close()
    with open(os.path.join(folder, file[:-4] + '.json'), 'w') as handle:
        json.dump({'body': body, 'radius': radius, 'file': file, 'max': radius / 100}, handle)


def test_the_map_of_the_flown_radius_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'MAPS_DIR', str(tmp_path))
    write_map(tmp_path, 'Mun', 200000.0)          # stock
    write_map(tmp_path, 'Mun', 400000.0)          # JNSQ, sorted after it: used to hide it
    bodies = {'Mun': {'radius': 200000.0}, 'Minmus': {'radius': 60000.0}}
    maps = service.list_maps(bodies)
    assert maps['Mun']['file'] == 'Mun-200000-r3.png'
    assert 'Minmus' not in maps                   # its map is not made yet: none rather than another install's


def test_a_map_on_disk_is_not_made_again(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'MAPS_DIR', str(tmp_path))
    write_map(tmp_path, 'Mun', 200000.0)
    write_map(tmp_path, 'Mun', 400000.0)
    assert service.map_file('Mun', 200000.0) in service.map_files()
