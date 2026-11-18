"""SCIENCE panel: step through the craft's experiments; run, transmit, dump or reset the one shown."""
from .. import settings as S
from ..display_format import fit_number
from ..messages import PanelOutputs

ACTIONS = {'sci_run': 'run', 'sci_transmit': 'transmit', 'sci_dump': 'dump', 'sci_reset': 'reset'}
LAMPS = ['led_sci_ready', 'led_sci_data', 'led_sci_spent']
DISPLAYS = ['disp_sci_number', 'disp_sci_value', 'disp_sci_transmit']
TEXTS = {'txt_sci': S.EXPERIMENT_NAME_CHARACTERS, 'txt_biome': S.BIOME_NAME_CHARACTERS}


def experiments(cockpit):
    return cockpit.telemetry.get('tlm/science', {}).get('experiments') or []


def selected_index(cockpit):
    """The place of the experiment shown, or None on a craft without any."""
    count = len(experiments(cockpit))
    return cockpit.selected_experiment % count if count else None


def handle_input(cockpit, change):
    """Commands for a control of this panel, or None when the control belongs to another panel."""
    control = change.control
    if control in ('sci_prev', 'sci_next'):
        index = selected_index(cockpit)
        if change.pressed and index is not None:
            cockpit.selected_experiment = index + (1 if control == 'sci_next' else -1)
        return []
    if control == 'sci_run_all':
        return cockpit.command('cmd/science', {'all': True}) if change.pressed else []
    if control in ACTIONS:
        index = selected_index(cockpit)
        if not change.pressed or index is None:
            return []
        return cockpit.command('cmd/science', {'index': index, 'action': ACTIONS[control]})
    return None


def render(cockpit, wanted):
    outputs = PanelOutputs(wanted, S.SCIENCE_PANEL)
    if not cockpit.powered():
        outputs.all_dark(LAMPS, [*DISPLAYS, *TEXTS])
        return
    if cockpit.is_on('lamp_test'):
        outputs.all_lit(LAMPS, DISPLAYS)
        for name, characters in TEXTS.items():
            outputs.text(name, '*' * characters)
        return
    fresh = cockpit.telemetry_is_fresh()
    index = selected_index(cockpit) if fresh else None
    shown = experiments(cockpit)[index] if index is not None else {}
    biome = cockpit.telemetry.get('tlm/science', {}).get('biome') if fresh else None
    outputs.text('txt_sci', (shown.get('title') or 'NO EXPERIMENT').upper()[:S.EXPERIMENT_NAME_CHARACTERS])
    outputs.text('txt_biome', (biome or '').upper()[:S.BIOME_NAME_CHARACTERS])
    outputs.text('disp_sci_number', fit_number(index + 1 if index is not None else None, 0, 2))
    outputs.text('disp_sci_value', fit_number(shown.get('value'), 1, 5))
    outputs.text('disp_sci_transmit', fit_number(shown.get('transmit'), 1, 5))
    outputs.lamp('led_sci_ready', shown.get('available') and not shown.get('data') and not shown.get('inoperable'))
    outputs.lamp('led_sci_data', shown.get('data'))
    outputs.lamp('led_sci_spent', shown.get('inoperable'))
