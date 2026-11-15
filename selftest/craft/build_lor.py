"""Build "Mun LOR": an Apollo-style stack from stock craft parts, written into the save's Ships/VAB.

    python3 selftest/craft/build_lor.py [KSP_DIR] [SAVE]

Top to bottom (as launched):
  orbiter  = Kerbal X command stack (Mk1-3 pod, 3 seats; Mk16-XL chute; 2.5 m heat shield) with Kerbal 1-5's docking-port
             assembly on the chute (port, battery, port Jr on top), a new TD-25, a Rockomax adapter (2.5 → 1.25 m) and
             Kerbal 1-5's service module (TD-12, 4 RCS, FL-T400, Terrier); the Terrier sits on the lander's top port
  lander   = a full Kerbal 1-5 upper stack (Mk1 pod, chute, port Jr on top, RCS, FL-T400, Terrier, TD-12) with three
             LT-2 legs on its tank; its top port carries the orbiter (separation: the port's "decouple node")
  adapter  = Rockomax adapter 02 flipped (1.25 m up), dropped by the lander's bottom TD-12 before the descent
  launcher = Kerbal X without its command stack: TD-25, Rockomax16 + Poodle (translunar stage), core + boosters

v1 (the stock Two-Stage Lander) was 11 t and ~4 m wide: the stack had CdA ≈ 20 m² and could not reach orbit with the
Poodle stage left for TMI (selftest/gaps.md G13). This lander is 4.4 t and 1.25 m wide.

The craft's root is the lander's pod (so the orbiter's chain hangs reversed above it). Decouplers separate at their
explosive (top) node and stay with the part below it: the TD-25 under the Poodle tank leaves with the spent stage, the
lander's bottom TD-12 with the adapter. Node offsets come from the stock craft files (attN entries), since the v2 parts define their nodes in the models.
"""
import os, re, sys

# the KSP install: first argument, or the KSP_DIR environment variable
KSP = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('KSP_DIR')
if not KSP:
    sys.exit('usage: build_lor.py <KSP install folder> [save name]   (or set KSP_DIR)')
SAVE = sys.argv[2] if len(sys.argv) > 2 else 'claude'
VAB = os.path.join(KSP, 'Ships', 'VAB')
OUT = os.path.join(KSP, 'saves', SAVE, 'Ships', 'VAB', 'Mun LOR.craft')

JR_TOP = 0.1474114              # docking port Jr: docking face (top node); base at 0
TD12 = 0.05                     # TD-12 nodes ±0.05
ADAPTER = 0.1892163             # Rockomax adapter 02 nodes ±0.189
TD25 = 0.1                      # TD-25 nodes ±0.1
CHUTE_GAP = 0.35                # lift the port assembly clear of the bigger Mk16-XL chute


class Part:
    def __init__(self, text):
        self.text = text
        self.id = re.search(r'\n\tpart = (\S+)', '\n' + text).group(1)

    def get(self, key):
        m = re.search(r'\n\t' + key + r' = (.*)', '\n' + self.text)
        return m.group(1) if m else None

    def set(self, key, value):
        self.text = re.sub(r'(\n\t' + key + r' = ).*', lambda m: m.group(1) + str(value), '\n' + self.text, count=1)[1:]

    def pos(self):
        return [float(x) for x in self.get('pos').split(',')]

    def place(self, x, y, z):
        self.set('pos', f'{x:.7g},{y:.7g},{z:.7g}')

    def move(self, dx, dy, dz):
        x, y, z = self.pos()
        self.place(x + dx, y + dy, z + dz)

    def lines_replace(self, key, values):
        """Replace every `key = ...` line by `values`, at the place of the first one (or before attN/srfN/EVENTS)."""
        lines = self.text.split('\n')
        idx = [i for i, l in enumerate(lines) if l.startswith(f'\t{key} = ')]
        if idx:
            at = idx[0]
            lines = [l for i, l in enumerate(lines) if i not in idx]
        else:
            order = {'link': ('\tattN = ', '\tsrfN = ', '\tEVENTS', '\tmass = ', '\tshielded = '),
                     'attN': ('\tsrfN = ', '\tEVENTS', '\tmass = ', '\tshielded = '),
                     'srfN': ('\tEVENTS', '\tmass = ', '\tshielded = ')}[key]
            at = next(i for i, l in enumerate(lines) if l.startswith(order))
        self.text = '\n'.join(lines[:at] + [f'\t{key} = {v}' for v in values] + lines[at:])

    def attn(self):
        return re.findall(r'\n\tattN = (.*)', '\n' + self.text)

    def srfn(self):
        return re.findall(r'\n\tsrfN = (.*)', '\n' + self.text)


def load(name):
    s = open(os.path.join(VAB, name)).read()
    head, *blocks = re.split(r'\nPART\n\{\n', s)
    parts = [Part(b[:b.rindex('}')].rstrip('\n')) for b in blocks]
    return head, parts


def clone(p, ren):
    t = p.text
    for a, b in ren.items():
        t = t.replace(a, b)
    return Part(t)


def main():
    _, k15 = load('Kerbal 1-5.craft')
    kx_head, kx = load('Kerbal X.craft')
    K = {p.id: p for p in k15}
    X = {p.id: p for p in kx}
    parts, parent = {}, {}             # id → Part ; id → parent id (None for the root)

    def add(p, par):
        assert p.id not in parts, p.id
        parts[p.id] = p
        parent[p.id] = par

    # ---------- lander: Kerbal 1-5 upper stack, ids renamed _4294… → _4292… ----------
    lander_ids = ['mk1pod.v2_4294620364', 'Decoupler.1_4294606904', 'parachuteSingle_4294606234', 'longAntenna_4294609504',
                  'dockingPort3_4294205130', 'batteryBankMini_4294259720', 'dockingPort3_4294236886', 'radialRCSTank_4294160246',
                  'RCSBlock_4294066032', 'RCSBlock_4294604224', 'RCSBlock_4294604160', 'RCSBlock_4294604096',
                  'fuelTank_4294189656', 'liquidEngine3.v2_4294583320', 'Decoupler.1_4294574396']
    L = lambda i: i.replace('_4294', '_4292')
    ren = {i: L(i) for i in lander_ids}
    k15_parent = {}
    for p in k15:
        for c in re.findall(r'\n\tlink = (.*)', '\n' + p.text):
            k15_parent[c] = p.id
    for i in lander_ids:
        add(clone(K[i], ren), L(k15_parent[i]) if i in k15_parent else None)
    lp = lambda i: parts[L(i)]
    # three LT-2 legs (Kerbal X's, radius scaled to the FL-T400), low on the lander's tank
    tank = lp('fuelTank_4294189656')
    y_leg = tank.pos()[1] - 0.86
    for n, lid in enumerate(['landingLeg1-2_4294188914', 'landingLeg1-2_4293671570', 'landingLeg1-2_4293671452']):
        nid = f'landingLeg1-2_429110000{n}'
        leg = clone(X[lid], {'landingLeg1-2_4294188914': 'landingLeg1-2_4291100000', 'landingLeg1-2_4293671570': 'landingLeg1-2_4291100001',
                             'landingLeg1-2_4293671452': 'landingLeg1-2_4291100002', 'Rockomax16.BW_4294219330': tank.id})
        x, _, z = X[lid].pos()
        k = (0.625 + 0.223) / 1.4731971
        leg.place(x * k, y_leg, z * k)
        leg.set('istg', 1); leg.set('dstg', 0)
        add(leg, tank.id)

    # ---------- orbiter: Kerbal X command stack + Kerbal 1-5 port assembly + new TD-25 + adapter + K1-5 service module ----------
    # no TD-12 under the orbiter's Terrier: a TD-12 keeps its lower side, so it stayed on the lander's docking face
    # after TMI (G14). The Terrier sits on the lander's port; the separation is the port's "decouple node" (undock).
    sm_ids = ['Decoupler.1_4294606904', 'RCSBlock_4294066032', 'RCSBlock_4294604224', 'RCSBlock_4294604160',
              'RCSBlock_4294604096', 'fuelTank_4294189656', 'liquidEngine3.v2_4294583320']
    TERRIER_BOTTOM = -0.81781
    port_ids = ['dockingPort3_4294205130', 'batteryBankMini_4294259720', 'dockingPort3_4294236886', 'radialRCSTank_4294160246']
    # stack positions, from the lander's top port upwards
    y = lp('dockingPort3_4294236886').pos()[1] + JR_TOP - TERRIER_BOTTOM  # orbiter's Terrier on the lander's port
    dy_sm = y - K['liquidEngine3.v2_4294583320'].pos()[1]
    for i in sm_ids:
        p = clone(K[i], {})
        p.move(0, dy_sm, 0)
        parts[p.id] = p
    y_ad = parts['Decoupler.1_4294606904'].pos()[1] + TD12 + ADAPTER          # adapter (2.5 m up, 1.25 m down)
    lander_craft = open(os.path.join(VAB, 'Two-Stage Lander.craft')).read()
    ad_text = re.search(r'\nPART\n\{\n(\tpart = largeAdapter2_4293305972\n.*?)\n\}', lander_craft, re.S).group(1)
    ad_orb = Part(ad_text.replace('largeAdapter2_4293305972', 'largeAdapter2_4291000004'))
    ad_orb.place(0, y_ad, 0)
    for k in ('rot', 'attRot', 'attRot0'):
        ad_orb.set(k, '0,0,0,1')
    td25 = clone(X['Decoupler.2_4294282032'], {'Decoupler.2_4294282032': 'Decoupler.2_4291000003'})
    y_td25 = y_ad + ADAPTER + TD25
    td25.place(0, y_td25, 0)
    dy_cm = (y_td25 + TD25) - X['HeatShield2_4294294368'].pos()[1]
    cm = {i: clone(X[i], {}) for i in ('HeatShield2_4294294368', 'mk1-3pod_4294320818', 'parachuteLarge_4294312400')}
    for p in cm.values():
        p.move(0, dy_cm, 0)
    chute_y = cm['parachuteLarge_4294312400'].pos()[1]
    k_chute_y = K['parachuteSingle_4294606234'].pos()[1]
    po = {i: clone(K[i], {}) for i in port_ids}
    for i, p in po.items():
        p.move(0, chute_y - k_chute_y + CHUTE_GAP, 0)
    # orbiter tree (reversed chain: lander top port → TD-12 → Terrier → tank → TD-12 → adapter → TD-25 → shield → pod → chute)
    chain = [L('dockingPort3_4294236886'), 'liquidEngine3.v2_4294583320', 'fuelTank_4294189656',
             'Decoupler.1_4294606904', 'largeAdapter2_4291000004', 'Decoupler.2_4291000003', 'HeatShield2_4294294368',
             'mk1-3pod_4294320818', 'parachuteLarge_4294312400']
    for p in [ad_orb, td25, *cm.values()]:
        parts[p.id] = p
    for a, b in zip(chain, chain[1:]):
        parent[b] = a
    for r in ('RCSBlock_4294066032', 'RCSBlock_4294604224', 'RCSBlock_4294604160', 'RCSBlock_4294604096'):
        parent[r] = 'Decoupler.1_4294606904'
    for i, p in po.items():
        parts[i] = p
    parent['dockingPort3_4294205130'] = 'parachuteLarge_4294312400'
    parent['batteryBankMini_4294259720'] = 'dockingPort3_4294205130'
    parent['dockingPort3_4294236886'] = 'batteryBankMini_4294259720'
    parent['radialRCSTank_4294160246'] = 'batteryBankMini_4294259720'
    po['dockingPort3_4294205130'].lines_replace('srfN', ['srfAttach,parachuteLarge_4294312400'])
    # node connections (attN), both ways
    parts['liquidEngine3.v2_4294583320'].lines_replace('attN', ['top,fuelTank_4294189656_0|0|0',
                                                               f"bottom,{L('dockingPort3_4294236886')}_0|{TERRIER_BOTTOM}|0"])
    lp('dockingPort3_4294236886').lines_replace('attN', [f"bottom,{L('batteryBankMini_4294259720')}_0|0|0",
                                                       f'top,liquidEngine3.v2_4294583320_0|{JR_TOP}|0'])
    parts['Decoupler.1_4294606904'].lines_replace('attN', ['top,largeAdapter2_4291000004_0|0.05|0',
                                                          'bottom,fuelTank_4294189656_0|-0.05|0'])
    ad_orb.lines_replace('attN', [f'top,Decoupler.2_4291000003_0|{ADAPTER}|0', f'bottom,Decoupler.1_4294606904_0|-{ADAPTER}|0'])
    td25.lines_replace('attN', ['top,HeatShield2_4294294368_0|0.1|0', 'bottom,largeAdapter2_4291000004_0|-0.1|0'])
    cm['HeatShield2_4294294368'].lines_replace('attN', ['direct,Decoupler.2_4291000003_0|0|0', 'top,mk1-3pod_4294320818_0|0.034|0'])

    # ---------- lander bottom: flipped adapter, then the launcher ----------
    td12_l = lp('Decoupler.1_4294574396')
    y_ad2 = td12_l.pos()[1] - TD12 - ADAPTER
    ad_low = Part(ad_text.replace('largeAdapter2_4293305972', 'largeAdapter2_4291000002'))
    ad_low.place(0, y_ad2, 0)
    for k in ('rot', 'attRot', 'attRot0'):
        ad_low.set(k, '1,0,0,0')                     # 180° about x: the 1.25 m end up
    ad_low.lines_replace('attN', [f"bottom,{td12_l.id}_0|{ADAPTER}|0", f'top,Decoupler.2_4294282032_0|-{ADAPTER}|0'])
    add(ad_low, td12_l.id)
    td12_l.lines_replace('attN', [f"top,{L('liquidEngine3.v2_4294583320')}_0|0.05|0", 'bottom,largeAdapter2_4291000002_0|-0.05|0'])
    for i in ('mk1-3pod_4294320818', 'parachuteLarge_4294312400', 'HeatShield2_4294294368'):
        del X[i]
    kx_parent = {}
    for p in kx:
        for c in re.findall(r'\n\tlink = (.*)', '\n' + p.text):
            kx_parent[c] = p.id
    dyx = (y_ad2 - ADAPTER - TD25) - X['Decoupler.2_4294282032'].pos()[1]
    remap = {7: 9, 6: 8, 5: 7, 4: 6, 3: 5, 2: 4, 1: 2}
    for i, p in X.items():
        p.move(0, dyx, 0)
        s = int(p.get('istg'))
        if s in remap:
            p.set('istg', remap[s])
            if int(p.get('sqor')) >= 0:
                p.set('sqor', remap[s])
        add(p, 'largeAdapter2_4291000002' if i == 'Decoupler.2_4294282032' else kx_parent[i])
    X['Decoupler.2_4294282032'].lines_replace('attN', ['top,largeAdapter2_4291000002_0|0.1|0', 'bottom,Rockomax16.BW_4294219330_0|-0.1|0'])

    # ---------- staging: the launcher keeps its order (9 … 4); orbiter separation + its engine 3; TMI stage drop 2 ----------
    for i, s in (('liquidEngine3.v2_4294583320', 3),):
        parts[i].set('istg', s); parts[i].set('sqor', s)
    for i in (L('liquidEngine3.v2_4294583320'), L('Decoupler.1_4294574396')):
        parts[i].set('istg', 1); parts[i].set('sqor', 1)
    parts['Decoupler.2_4291000003'].set('istg', 0); parts['Decoupler.2_4291000003'].set('sqor', 0)

    # ---------- stiffness: v2 bent at the docking ports and TD-12s and lost control at 3.6 km (gaps.md G14) ----------
    # every part above the launcher core: autostrut to the heaviest part, rigid attachment
    core_and_below = set()
    def below(i):
        core_and_below.add(i)
        for c, p in parent.items():
            if p == i:
                below(c)
    below('Decoupler.2_4294169290')                 # Kerbal X core decoupler: the core, boosters, clamps
    for i, p in parts.items():
        if i not in core_and_below:
            p.set('autostrutMode', 'Heaviest')
            p.set('rigidAttachment', 'True')

    # ---------- links from the parent map ----------
    children = {i: [] for i in parts}
    for c, p in parent.items():
        if p is not None:
            children[p].append(c)
    roots = [i for i, p in parent.items() if p is None]
    assert roots == [L('mk1pod.v2_4294620364')], roots
    assert set(parent) == set(parts), set(parts) ^ set(parent)
    for i, p in parts.items():
        p.lines_replace('link', children[i])
    # every reference must resolve
    for p in parts.values():
        for ref in [e.split(',')[1].rsplit('_', 1)[0] for e in p.attn() if ',' in e] + [e.split(',')[1] for e in p.srfn()]:
            assert ref in parts, (p.id, ref)

    # order: depth-first from the root (KSP lists parts that way)
    order = []
    def walk(i):
        order.append(i)
        for c in children[i]:
            walk(c)
    walk(roots[0])
    head = re.sub(r'ship = .*', 'ship = Mun LOR', kx_head, count=1)
    head = re.sub(r'description = .*', 'description = Orbiter (Mk1-3 command module + service module) and a Kerbal 1-5 lander '
                  'on a Kerbal X launcher, Apollo-style. Built by selftest/craft/build_lor.py.', head, count=1)
    head = re.sub(r'vesselType = .*', 'vesselType = Ship', head, count=1)
    with open(OUT, 'w') as f:
        f.write(head)
        for i in order:
            f.write('\nPART\n{\n' + parts[i].text + '\n}')
        f.write('\n')
    ys = [parts[i].pos()[1] for i in order]
    print(f'wrote {OUT}: {len(order)} parts, height {max(ys) - min(ys):.1f} m')


if __name__ == '__main__':
    main()
