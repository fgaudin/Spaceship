"""Build "AcapelloCams IU": the AcapelloCams craft with an Instrument Unit on its Skiff stage, written next to it.

    python3 selftest/craft/build_acapello_iu.py [KSP_DIR] [SAVE]

Why: after the CSM separates for the transposition, nothing on the stack (Skiff stage and M.E.M.) can command
its reaction wheels, since the M.E.M. flies uncrewed and has no probe core. The stack keeps the slow tumble the
separation gave it (0.4 °/s measured), and chasing its port emptied the CSM's monopropellant. Apollo's S-IVB held
its attitude with its Instrument Unit; this one is an RC-L01 probe core (SAS level 3, 30 EC) and an Advanced
Inline Stabilizer (15 kN·m), both surface-attached to the Skiff stage's Mk3 tank and clipped inside it (parts of one
vessel do not collide). They stay with the spent stage at the extraction (the TD-06 above the tank).

The original craft is not changed.
"""
import os, re, sys

KSP = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('KSP_DIR')
if not KSP:
    sys.exit('usage: build_acapello_iu.py <KSP install folder> [save name]   (or set KSP_DIR)')
SAVE = sys.argv[2] if len(sys.argv) > 2 else 'claude'
VAB = os.path.join(KSP, 'saves', SAVE, 'Ships', 'VAB')
SOURCE, OUTPUT = os.path.join(VAB, 'AcapelloCams.craft'), os.path.join(VAB, 'AcapelloCams IU.craft')
TANK = 'mk3FuselageLFO.25_4293173622'          # the Skiff stage's tank, under the TD-06 that carries the lander
NEW_PARTS = [                                  # (part name, craft id, offset from the tank's centre, metres)
    ('probeStackLarge', 4293100001, (0.6, 0.3, 0.0)),
    ('asasmodule1-2', 4293100002, (-0.6, -0.3, 0.0)),
]


def blocks(text):
    """The craft's top-level PART blocks, as (start, end) character spans."""
    spans, depth, start = [], 0, None
    for match in re.finditer(r'^(PART)$|^\{$|^\}$', text, re.M):
        token = match.group(0)
        if token == 'PART':
            start = match.start()
        elif token == '{':
            depth += 1
        else:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, match.end()))
                start = None
    return spans


def field(block, name):
    found = re.search(rf'^\t{name} = (.*)$', block, re.M)
    return found.group(1) if found else None


def part_block(name, craft_id, position, tank_block, offset):
    stages = {key: field(tank_block, key) for key in ('istg', 'dstg', 'sepI')}
    position_text = ','.join(f'{value:.6f}' for value in position)
    offset_text = '|'.join(f'{value:.3f}' for value in offset)
    return f"""PART
{{
\tpart = {name}_{craft_id}
\tpartName = Part
\tpersistentId = {craft_id % 1000000000}
\tpos = {position_text}
\tattPos = 0,0,0
\tattPos0 = {offset_text.replace('|', ',')}
\trot = 0,0,0,1
\tattRot = 0,0,0,1
\tattRot0 = 0,0,0,1
\tmir = 1,1,1
\tsymMethod = Radial
\tautostrutMode = Off
\trigidAttachment = False
\tistg = {stages['istg']}
\tresPri = 0
\tdstg = {stages['dstg']}
\tsidx = -1
\tsqor = -1
\tsepI = {stages['sepI']}
\tattm = 1
\tsameVesselCollision = False
\tmodCost = 0
\tmodMass = 0
\tmodSize = 0,0,0
\tsrfN = srfAttach,{TANK},,{offset_text},1|0|0,{offset_text}
}}
"""


def main():
    text = open(SOURCE).read()
    spans = blocks(text)
    tank_span = next(span for span in spans if f'part = {TANK}\n' in text[span[0]:span[1]])
    tank_block = text[tank_span[0]:tank_span[1]]
    tank_position = [float(value) for value in field(tank_block, 'pos').split(',')]
    # the tank links to its new children
    links = ''.join(f'\tlink = {name}_{craft_id}\n' for name, craft_id, _ in NEW_PARTS)
    first_link = re.search(r'^\tlink = .*\n', tank_block, re.M)
    new_tank = tank_block[:first_link.end()] + links + tank_block[first_link.end():]
    new_parts = ''.join(part_block(name, craft_id, [p + o for p, o in zip(tank_position, offset)], tank_block, offset)
                        for name, craft_id, offset in NEW_PARTS)
    text = text[:tank_span[0]] + new_tank + '\n' + new_parts + text[tank_span[1]:]
    text = re.sub(r'^ship = .*$', 'ship = AcapelloCams IU', text, count=1, flags=re.M)
    open(OUTPUT, 'w').write(text)
    print(f'wrote {OUTPUT}: {len(NEW_PARTS)} parts added on {TANK}')


if __name__ == '__main__':
    main()
