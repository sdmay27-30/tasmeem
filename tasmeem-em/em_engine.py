# TASMEEM EM engine: turns a project (board, shapes, port) into an openEMS
# simulation, runs it, and saves the results. The GUI (tasmeem_em.py) calls this
# file in the background, so the user never writes or sees the script.
#
# Command line use (what the GUI runs):
#   python3 em_engine.py run    project.json  output_folder
#   python3 em_engine.py export project.json  output_folder   (model only, for AppCSXCAD)
#   python3 em_engine.py script project.json  script.py       (editable openEMS script)
#   python3 em_engine.py farfield project.json run_folder f_GHz  (3D far field of a finished run)

import json
import math
import os
import sys
import time

import numpy as np

# Windows version: openEMS's DLLs are in the openEMS folder next to the app folder
if os.name == "nt":
    _oe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openEMS")
    if os.path.isdir(_oe):
        os.environ.setdefault("CSXCAD_INSTALL_PATH", _oe)

C0 = 299792458.0
EPS0 = 8.8541878128e-12

MESH_QUALITY = {
    # name: (cells per wavelength, metal edge resolution in mm)
    "coarse": (15, 1.0),
    "normal": (20, 0.5),
    "fine": (30, 0.25),
}
# openEMS runs until the energy in the model has fallen by 40 dB (END_CRITERIA). Stopping earlier
# (the original Octave script stopped at 40000 steps) leaves energy in the antenna and shifts the
# resonance, the S11 depth and especially the efficiency. MAX_TIMESTEPS is only a safety cap.
MAX_TIMESTEPS = {"coarse": 1000000, "normal": 1000000, "fine": 1000000}
END_CRITERIA = 1e-4          # stop when the energy has fallen by 40 dB

FF_THETA = np.arange(0.0, 181.0, 2.0)      # 3D far-field grid (degrees), same theta steps as the cuts
FF_PHI = np.arange(0.0, 361.0, 5.0)


def excitation(f_start, f_stop):
    """Center and half width (Hz) of the Gaussian test pulse. It always covers the
    whole range the user asked for, with 20% spare on each side."""
    f0 = (f_start + f_stop) / 2
    fc = max(f0 / 2.4, 0.6 * (f_stop - f_start))
    if fc > f0:                # very wide range: start the pulse at DC instead
        f0 = fc = 0.6 * f_stop
    return f0, fc


# ---------------------------------------------------------------- project

def patch_template(PL=29.5, PW=38.0, MW=2.86, InL=9.0, InW=0.74, SL=59.0, SW=76.0):
    """The inset-fed patch from the CST comparison, built from rectangles."""
    xin = PL / 2 - InL                      # where the notches start
    side_y = (MW / 2 + InW + PW / 2) / 2    # center of each side piece
    side_w = PW / 2 - (MW / 2 + InW)        # width of each side piece
    shapes = [
        {"type": "rectangle", "name": "Patch body", "x": (-PL / 2 + xin) / 2, "y": 0.0,
         "length": xin + PL / 2, "width": PW},
        {"type": "rectangle", "name": "Patch side (top)", "x": (xin + PL / 2) / 2, "y": side_y,
         "length": PL / 2 - xin, "width": side_w},
        {"type": "rectangle", "name": "Patch side (bottom)", "x": (xin + PL / 2) / 2, "y": -side_y,
         "length": PL / 2 - xin, "width": side_w},
        {"type": "rectangle", "name": "Feed line", "x": (xin + SL / 2) / 2, "y": 0.0,
         "length": SL / 2 - xin, "width": MW},
    ]
    port = {"x": SL / 2, "y": 0.0, "width": MW, "length": 10.0, "direction": "-x", "impedance": 50.0}
    return shapes, port


SHAPE_KEYS = {"rectangle": ["x", "y", "length", "width"],
              "taper": ["start", "end", "center", "width1", "width2"],
              "arc": ["x", "y", "r_inner", "r_outer", "angle_start", "angle_stop"]}


def clean_project(p):
    """Check a design read from a .json file before using it. Returns (design, None) with every
    value as a number and missing optional values filled in, or (None, what is wrong)."""
    def num(d, key, where, default=None):
        v = d.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("%s: '%s' must be a number%s" % (where, key, "" if key in d else " (it is missing)"))
        return float(v)
    try:
        if not isinstance(p, dict) or not isinstance(p.get("board"), dict) or not isinstance(p.get("shapes"), list):
            raise ValueError("a design needs a 'board' section and a 'shapes' list.")
        q = dict(p)
        q["name"] = str(p.get("name") or "design")
        b = p["board"]
        q["board"] = {k: num(b, k, "board", 0.0) for k in ("length", "width", "thickness", "epsR", "tanD")}
        q["board"]["ground"] = bool(b.get("ground", True))
        f = p.get("freq", {})
        if not isinstance(f, dict):
            raise ValueError("'freq' must have a start and a stop.")
        q["freq"] = {"start": num(f, "start", "freq", 0.0), "stop": num(f, "stop", "freq", 0.0)}
        q["mesh"] = p.get("mesh", "normal")
        if q["mesh"] not in MESH_QUALITY:
            raise ValueError("'mesh' must be \"coarse\", \"normal\" or \"fine\".")
        ab = p.get("airbox")
        ok = isinstance(ab, list) and len(ab) == 3 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in ab)
        q["airbox"] = [float(v) for v in ab] if ok else [0.0, 0.0, 0.0]
        q["shapes"] = []
        for i, s in enumerate(p["shapes"], 1):
            if not isinstance(s, dict) or s.get("type") not in SHAPE_KEYS:
                raise ValueError("shape %d: 'type' must be \"rectangle\", \"taper\" or \"arc\"." % i)
            t = dict(s)
            t["name"] = str(s.get("name") or "%s %d" % (s["type"].capitalize(), i))
            for k in SHAPE_KEYS[s["type"]]:
                t[k] = num(s, k, "shape '%s'" % t["name"])
            if s["type"] == "taper":
                t["axis"] = s.get("axis", "x")
                if t["axis"] not in ("x", "y"):
                    raise ValueError("shape '%s': 'axis' must be \"x\" or \"y\"." % t["name"])
            q["shapes"].append(t)
        pt = p.get("port")
        if pt is not None:
            if not isinstance(pt, dict):
                raise ValueError("'port' must be a section with x, y, width, length and direction.")
            q["port"] = {k: num(pt, k, "port") for k in ("x", "y", "width", "length")}
            q["port"]["impedance"] = num(pt, "impedance", "port", 50.0)
            q["port"]["direction"] = pt.get("direction")
            if q["port"]["direction"] not in ("+x", "-x", "+y", "-y"):
                raise ValueError("port: 'direction' must be \"+x\", \"-x\", \"+y\" or \"-y\".")
        else:
            q["port"] = None
        return q, None
    except ValueError as e:
        return None, str(e)


def default_project():
    shapes, port = patch_template()
    return {
        "name": "Inset-fed patch 2.4 GHz",
        "board": {"length": 59.0, "width": 76.0, "thickness": 1.5, "epsR": 4.3, "tanD": 0.025,
                  "ground": True},
        "airbox": [200.0, 200.0, 150.0],
        "freq": {"start": 2.2, "stop": 2.6},
        "mesh": "normal",
        "shapes": shapes,
        "port": port,
    }


def shape_outline(s, arc_steps=36):
    """2D outline (list of x, list of y) of a shape, in mm."""
    if s["type"] == "rectangle":
        x0, x1 = s["x"] - s["length"] / 2, s["x"] + s["length"] / 2
        y0, y1 = s["y"] - s["width"] / 2, s["y"] + s["width"] / 2
        return [x0, x1, x1, x0], [y0, y0, y1, y1]
    if s["type"] == "taper":
        # trapezoid from (x1, width1) to (x2, width2), centered on y (or the same along y)
        a1, a2, c = s["start"], s["end"], s["center"]
        w1, w2 = s["width1"] / 2, s["width2"] / 2
        u = [a1, a2, a2, a1]
        v = [c - w1, c - w2, c + w2, c + w1]
        if s.get("axis", "x") == "x":
            return u, v
        return v, u
    if s["type"] == "arc":
        a0 = math.radians(s["angle_start"])
        a1 = math.radians(s["angle_stop"])
        t = np.linspace(a0, a1, arc_steps + 1)
        xo = s["x"] + s["r_outer"] * np.cos(t)
        yo = s["y"] + s["r_outer"] * np.sin(t)
        xi = s["x"] + s["r_inner"] * np.cos(t[::-1])
        yi = s["y"] + s["r_inner"] * np.sin(t[::-1])
        return list(np.concatenate([xo, xi])), list(np.concatenate([yo, yi]))
    raise ValueError("unknown shape type: " + str(s["type"]))


def point_in_shape(x, y, s, tol=1e-6):
    """True if (x, y) is inside the shape or on its edge."""
    xs, ys = shape_outline(s, 72)
    n = len(xs)
    inside = False
    for i in range(n):
        x1, y1, x2, y2 = xs[i], ys[i], xs[(i + 1) % n], ys[(i + 1) % n]
        # on this edge?
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 > 0:
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
            if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= tol:
                return True
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def copper_width_at(x, y, ux, uy, s):
    """Width of shape s across the direction (ux, uy) at the point (x, y)."""
    vx, vy = -uy, ux                      # across the feed
    xs, ys = shape_outline(s, 72)
    n = len(xs)
    hits = []
    for i in range(n):
        x1, y1, x2, y2 = xs[i], ys[i], xs[(i + 1) % n], ys[(i + 1) % n]
        # solve (x, y) + t (vx, vy) = (x1, y1) + u (x2 - x1, y2 - y1)
        ex, ey = x2 - x1, y2 - y1
        det = vx * (-ey) - vy * (-ex)
        if abs(det) < 1e-12:
            continue
        t = ((x1 - x) * (-ey) - (y1 - y) * (-ex)) / det
        u = (vx * (y1 - y) - vy * (x1 - x)) / det
        if -1e-9 <= u <= 1 + 1e-9:
            hits.append(t)
    below = [t for t in hits if t <= 1e-9]
    above = [t for t in hits if t >= -1e-9]
    if not below or not above:
        return None
    return min(above) - max(below)


def port_ends(pt):
    """Start point, inner end point and unit direction (ux, uy) of the port."""
    sign = -1 if pt["direction"].startswith("-") else 1
    ux, uy = (sign, 0) if pt["direction"][1] == "x" else (0, sign)
    x0, y0 = pt["x"], pt["y"]
    return (x0, y0), (x0 + ux * pt["length"], y0 + uy * pt["length"]), (ux, uy)


def port_status(p):
    """(connected, width of the copper the port connects to or None, shape name or None)."""
    pt = p["port"]
    if not pt:
        return False, None, None
    _, (xe, ye), (ux, uy) = port_ends(pt)
    # look just past the inner end of the port, along the feed
    for d in (0.01, 0.0, -0.01):
        xt, yt = xe + ux * d, ye + uy * d
        for s in p["shapes"]:
            if s.get("hidden"):
                continue
            if point_in_shape(xt, yt, s):
                return True, copper_width_at(xt, yt, ux, uy, s), s["name"]
    return False, None, None


def edge_lines(p):
    """The x and y positions of all copper and port edges (what the mesh must resolve)."""
    xl, yl = [], []
    for s in p["shapes"]:
        xs, ys = shape_outline(s)
        if s["type"] == "rectangle":
            xl += [min(xs), max(xs)]
            yl += [min(ys), max(ys)]
        else:
            lx, ly = polygon_mesh_lines(xs, ys, 1e9)       # outline lines only, no fill
            xl += lx
            yl += ly
    pt = p["port"]
    if pt:
        (x0, y0), (x1, y1), (ux, uy) = port_ends(pt)
        if ux:
            xl += [x0, x1]
            yl += [y0 - pt["width"] / 2, y0 + pt["width"] / 2]
        else:
            yl += [y0, y1]
            xl += [x0 - pt["width"] / 2, x0 + pt["width"] / 2]
    return xl, yl


def smallest_gap(lines):
    v = sorted(set(round(float(a), 9) for a in lines))
    gaps = [b - a for a, b in zip(v[:-1], v[1:]) if b - a > 1e-6]
    return min(gaps) if gaps else None


def estimate_cells(p):
    """Rough number of mesh cells, from the same lines the real mesh uses (before the
    extra lines openEMS adds around metal edges)."""
    b, ab = p["board"], p["airbox"]
    f0, fc = excitation(p["freq"]["start"] * 1e9, p["freq"]["stop"] * 1e9)
    cells, edge_res = MESH_QUALITY[p.get("mesh", "normal")]
    max_res = C0 / (f0 + fc) / 1e-3 / cells
    xl, yl = edge_lines(p)
    for s in p["shapes"]:
        xs, ys = shape_outline(s)
        if s["type"] == "rectangle":      # openEMS adds lines 1/3 and 2/3 of edge_res around metal edges
            for lines, lo, hi in ((xl, min(xs), max(xs)), (yl, min(ys), max(ys))):
                lines += [lo - edge_res / 3, lo + 2 * edge_res / 3, hi + edge_res / 3, hi - 2 * edge_res / 3]
        else:                             # tapers and arcs also get the even fill lines
            lx, ly = polygon_mesh_lines(xs, ys, edge_res)
            xl += lx
            yl += ly
    xl += [-ab[0] / 2, ab[0] / 2, -b["length"] / 2, b["length"] / 2]
    yl += [-ab[1] / 2, ab[1] / 2, -b["width"] / 2, b["width"] / 2]
    zl = [-ab[2] / 3, ab[2] * 2 / 3] + list(np.linspace(0, b["thickness"], 5))
    n = 1
    for lines in (xl, yl, zl):
        n *= len(smooth_lines(merge_close(lines, edge_res / 10), max_res, 1.4))
    return n


def check_project(p):
    """Problems that stop a run (empty list means OK to run). See check_warnings too."""
    problems = []
    b = p["board"]
    names = {"length": "length", "width": "width", "thickness": "thickness", "epsR": "permittivity"}
    for k in ["length", "width", "thickness", "epsR"]:
        if b[k] <= 0:
            problems.append("Step 1: enter the board " + names[k] + ".")
    if b["epsR"] > 0 and b["epsR"] < 1:
        problems.append("Step 1: the permittivity cannot be below 1.")
    if b["tanD"] < 0:
        problems.append("Step 1: the loss tangent cannot be negative.")
    fs, fe = p["freq"]["start"], p["freq"]["stop"]
    if fs <= 0 or fe <= 0:
        problems.append("Step 2: enter the start and stop frequency.")
    elif fe <= fs:
        problems.append("Step 2: the stop frequency must be higher than the start frequency.")
    if not p["shapes"]:
        problems.append("Step 3: add at least one shape.")
    board_ok = b["length"] > 0 and b["width"] > 0
    min_gap = MESH_QUALITY[p.get("mesh", "normal")][1] / 10
    for s in p["shapes"]:
        nm = "'" + s["name"] + "'"
        if s["type"] == "rectangle":
            if s["length"] <= 0 or s["width"] <= 0:
                problems.append(nm + ": length and width must be more than 0.")
        elif s["type"] == "taper":
            if abs(s["end"] - s["start"]) < 1e-6:
                problems.append(nm + ": the start and end positions must be different.")
            if s["width1"] <= 0 or s["width2"] <= 0:
                problems.append(nm + ": both widths must be more than 0.")
        elif s["type"] == "arc":
            if s["r_inner"] < 0 or s["r_inner"] >= s["r_outer"]:
                problems.append(nm + ": the inner radius must be smaller than the outer radius.")
            span = abs(s["angle_stop"] - s["angle_start"])
            if span < 1e-6:
                problems.append(nm + ": the start and stop angles must be different.")
            elif span > 360 + 1e-6:
                problems.append(nm + ": the angle range cannot be more than 360 degrees.")
        else:
            problems.append(nm + ": unknown shape type.")
            continue
        xs, ys = shape_outline(s)
        outside = min(xs) < -b["length"] / 2 - 1e-6 or max(xs) > b["length"] / 2 + 1e-6 or \
            min(ys) < -b["width"] / 2 - 1e-6 or max(ys) > b["width"] / 2 + 1e-6
        if board_ok and outside:
            problems.append(nm + " goes past the edge of the board.")
        size = shape_min_size(s)
        if size is not None and 0 < size < min_gap:
            problems.append(nm + " is %.3g mm across, too small for the %s mesh (smallest %.3g mm). %s"
                            % (size, p.get("mesh", "normal"), min_gap,
                               "Use the fine mesh." if p.get("mesh") != "fine" else "Make it wider."))
    pt = p["port"]
    if pt is None:
        problems.append("Step 4: add a port (where the signal goes in).")
    else:
        if pt["width"] <= 0 or pt["length"] <= 0:
            problems.append("Step 4: the port width and length must be more than 0.")
        if pt.get("impedance", 50) <= 0:
            problems.append("Step 4: the port impedance must be more than 0.")
        (x0, y0), (x1, y1), (ux, uy) = port_ends(pt)
        hw = pt["width"] / 2
        if board_ok:
            xs = [x0, x1] + ([x0 - hw, x0 + hw] if uy else [])
            ys = [y0, y1] + ([y0 - hw, y0 + hw] if ux else [])
            if min(xs) < -b["length"] / 2 - 1e-6 or max(xs) > b["length"] / 2 + 1e-6 or \
               min(ys) < -b["width"] / 2 - 1e-6 or max(ys) > b["width"] / 2 + 1e-6:
                problems.append("Step 4: the port must be on the board. It runs from (%g, %g) to (%g, %g) mm; "
                                "check its start point and that it points into the board." % (x0, y0, x1, y1))
        if p["shapes"] and not port_status(p)[0]:
            problems.append("Step 4: the port is not connected to any copper. Its inner end at (%g, %g) mm "
                            "must touch a shape (usually the feed line)." % (x1, y1))
    ab = p["airbox"]
    if board_ok and (ab[0] <= b["length"] or ab[1] <= b["width"]):
        problems.append("The simulation box must be bigger than the board.")
    return problems


def shape_min_size(s):
    if s["type"] == "rectangle":
        return min(s["length"], s["width"])
    if s["type"] == "taper":
        return min(s["width1"], s["width2"], abs(s["end"] - s["start"]))
    if s["type"] == "arc":
        return s["r_outer"] - s["r_inner"]
    return None


def check_warnings(p):
    """Things that do not stop a run but are worth a second look. Call after check_project."""
    warn = []
    b, pt = p["board"], p["port"]
    if pt and p["shapes"]:
        ok, w, name = port_status(p)
        if ok and w is not None and abs(w - pt["width"]) > 0.1 * w:
            warn.append("The port is %g mm wide but '%s' is %.3g mm wide where they meet. They should match."
                        % (pt["width"], name, w))
        (x0, y0), _, (ux, uy) = port_ends(pt)
        at_edge = abs(abs(x0) - b["length"] / 2) < 0.01 if ux else abs(abs(y0) - b["width"] / 2) < 0.01
        if not at_edge:
            warn.append("The port does not start at the board edge. That is allowed, but a microstrip port is "
                        "normally placed where the feed line meets the edge.")
    min_gap = MESH_QUALITY[p.get("mesh", "normal")][1] / 10
    xl, yl = edge_lines(p)
    g = min([v for v in (smallest_gap(xl), smallest_gap(yl)) if v is not None], default=None)
    edge_res = MESH_QUALITY[p.get("mesh", "normal")][1]
    if g is not None and g < min_gap:
        warn.append("Some copper edges are only %.3g mm apart. The %s mesh treats edges closer than %.3g mm as one%s."
                    % (g, p.get("mesh", "normal"), min_gap,
                       ", so use the fine mesh" if p.get("mesh") != "fine" else ""))
    elif g is not None and g < edge_res - 1e-6:
        better = {"coarse": "normal or fine", "normal": "fine"}.get(p.get("mesh", "normal"))
        warn.append("The smallest gap or strip in the copper is %.3g mm, finer than the %s mesh's %.3g mm edge "
                    "resolution. The resonance will be close, but the S11 depth and bandwidth will be rough%s."
                    % (g, p.get("mesh", "normal"), edge_res, "; use the %s mesh for final numbers" % better
                       if better else ""))
    try:
        n = estimate_cells(p)
        if n > 20e6:
            warn.append("This needs about %.0f million mesh cells, which will take a very long time and a lot of "
                        "memory. Use a coarser mesh, a narrower frequency range, or a smaller board." % (n / 1e6))
    except Exception:
        pass
    return warn


# ---------------------------------------------------------------- mesh

def merge_close(lines, min_gap):
    """Replace groups of lines closer than min_gap with one line (the outer two are kept)."""
    L = sorted(float(v) for v in lines)
    groups = [[L[0]]]
    for v in L[1:]:
        if v - groups[-1][-1] < min_gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    out = [sum(g) / len(g) for g in groups]
    out[0], out[-1] = L[0], L[-1]
    return out


def smooth_lines(lines, max_res, ratio=1.4):
    """Fill in mesh lines between the fixed lines so that
    - no cell is bigger than max_res,
    - neighbouring cells change size by at most about `ratio`.
    Every fixed line wants small cells next to it (as small as the gap to its
    nearest fixed neighbour). Away from it the allowed cell size grows linearly,
    h(x) = d_i + (ratio - 1) * |x - x_i|, which is what geometric grading gives.
    Each gap gets as many cells as the integral of 1/h says, spaced by that integral."""
    import numpy as np
    L = np.array(sorted(set(round(float(v), 6) for v in lines)))
    if len(L) < 2:
        return list(L)
    g = np.diff(L)
    d = np.minimum(np.r_[g, max_res], np.r_[max_res, g])
    d = np.minimum(d, max_res)
    k = ratio - 1.0

    def h(x):
        return np.minimum(max_res, np.min(d[None, :] + k * np.abs(x[:, None] - L[None, :]), axis=1))

    out = [L[0]]
    for a, b in zip(L[:-1], L[1:]):
        xs = np.linspace(a, b, 400)
        w = np.r_[0, np.cumsum(0.5 * (1 / h(xs[1:]) + 1 / h(xs[:-1])) * np.diff(xs))]
        n = max(1, int(np.ceil(w[-1] - 0.05)))
        if n > 1:
            targets = np.linspace(0, w[-1], n + 1)[1:-1]
            out += list(np.interp(targets, w, xs))
        out.append(b)
    return [float(v) for v in out]


def polygon_mesh_lines(xs, ys, edge_res):
    """Mesh lines for a taper or arc: its outer extent, every straight edge that lies
    along x or y, and an even fill inside so curved or slanted edges are resolved."""
    lx, ly = [min(xs), max(xs)], [min(ys), max(ys)]
    n = len(xs)
    for i in range(n):
        j = (i + 1) % n
        if abs(xs[i] - xs[j]) < 1e-9:
            lx.append(xs[i])
        if abs(ys[i] - ys[j]) < 1e-9:
            ly.append(ys[i])
    fill = 2 * edge_res
    for lines, lo, hi in [(lx, min(xs), max(xs)), (ly, min(ys), max(ys))]:
        k = int((hi - lo) / fill)
        if k > 1:
            lines += list(np.linspace(lo, hi, k + 1)[1:-1])
    return lx, ly


def finish_mesh(mesh, f0, fc, cells, edge_res):
    """Merge lines that are too close, then fill in graded lines (see smooth_lines)."""
    max_res = C0 / (f0 + fc) / 1e-3 / cells
    min_gap = edge_res / 10      # lines closer than this are merged (tiny cells make the time step tiny)
    for ny in range(3):
        mesh.SetLines(ny, smooth_lines(merge_close(mesh.GetLines(ny), min_gap), max_res, 1.4))


def build_model(p):
    """Create the openEMS model. Returns (FDTD, CSX, port, nf2ff, freq_info)."""
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    b = p["board"]
    SL, SW, SH = b["length"], b["width"], b["thickness"]
    f_start, f_stop = p["freq"]["start"] * 1e9, p["freq"]["stop"] * 1e9
    f0, fc = excitation(f_start, f_stop)
    cells, edge_res = MESH_QUALITY[p.get("mesh", "normal")]

    FDTD = openEMS(NrTS=MAX_TIMESTEPS[p.get("mesh", "normal")], EndCriteria=END_CRITERIA)
    FDTD.SetGaussExcite(f0, fc)
    FDTD.SetBoundaryCond(["MUR"] * 6)

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(1e-3)               # all lengths in mm

    ab = p["airbox"]
    mesh.AddLine("x", [-ab[0] / 2, ab[0] / 2])
    mesh.AddLine("y", [-ab[1] / 2, ab[1] / 2])
    mesh.AddLine("z", [-ab[2] / 3, ab[2] * 2 / 3])

    # substrate
    kappa = b["tanD"] * 2 * math.pi * f0 * EPS0 * b["epsR"]
    substrate = CSX.AddMaterial("substrate", epsilon=b["epsR"], kappa=kappa)
    substrate.AddBox([-SL / 2, -SW / 2, 0], [SL / 2, SW / 2, SH], priority=0)
    mesh.AddLine("z", np.linspace(0, SH, 5))   # 4 cells through the substrate
    FDTD.AddEdges2Grid(dirs="xy", properties=substrate)

    # ground plane
    if b.get("ground", True):
        gnd = CSX.AddMetal("gnd")
        gnd.AddBox([-SL / 2, -SW / 2, 0], [SL / 2, SW / 2, 0], priority=10)

    # top metal: rectangles are boxes, tapers and arcs are polygons
    metal = CSX.AddMetal("metal")
    for s in p["shapes"]:
        xs, ys = shape_outline(s)
        if s["type"] == "rectangle":
            box = metal.AddBox([min(xs), min(ys), SH], [max(xs), max(ys), SH], priority=10)
            FDTD.AddEdges2Grid(dirs="xy", primitives=box, metal_edge_res=edge_res)
            mesh.AddLine("x", [min(xs), max(xs)])     # the metal edges themselves
            mesh.AddLine("y", [min(ys), max(ys)])
        else:
            metal.AddPolygon([xs, ys], "z", SH, priority=10)
            lx, ly = polygon_mesh_lines(xs, ys, edge_res)
            mesh.AddLine("x", lx)
            mesh.AddLine("y", ly)

    # port: extra lines across the strip and at its ends (needs the mesh first)
    pt = p["port"]
    d = pt["direction"]
    sign = -1 if d.startswith("-") else 1
    axis = d[1]
    if axis == "x":
        start = [pt["x"], pt["y"] - pt["width"] / 2, SH]
        stop = [pt["x"] + sign * pt["length"], pt["y"] + pt["width"] / 2, 0]
        mesh.AddLine("y", np.linspace(start[1], stop[1], 5))
        mesh.AddLine("x", [start[0], stop[0]])
    else:
        start = [pt["x"] - pt["width"] / 2, pt["y"], SH]
        stop = [pt["x"] + pt["width"] / 2, pt["y"] + sign * pt["length"], 0]
        mesh.AddLine("x", np.linspace(start[0], stop[0], 5))
        mesh.AddLine("y", [start[1], stop[1]])

    finish_mesh(mesh, f0, fc, cells, edge_res)

    port = FDTD.AddMSLPort(1, metal, start, stop, axis, "z", excite=1, FeedShift=2,
                           MeasPlaneShift=pt["length"] / 2, priority=999)
    nf2ff = FDTD.CreateNF2FFBox()
    return FDTD, CSX, port, nf2ff, (f0, fc, f_start, f_stop)


# ---------------------------------------------------------------- run

def export_model(p, out_dir):
    """Write the model to an XML file so AppCSXCAD can show it with the mesh."""
    os.makedirs(out_dir, exist_ok=True)
    FDTD, CSX, port, nf2ff, _ = build_model(p)
    xml = os.path.join(os.path.abspath(out_dir), "model.xml")
    CSX.Write2XML(xml)
    return xml


def run(p, out_dir):
    problems = check_project(p)
    if problems:
        raise SystemExit("Cannot run:\n" + "\n".join(problems))
    out_dir = os.path.abspath(out_dir)
    sim_dir = os.path.join(out_dir, "sim")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "project.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)

    print("TASMEEM: building the model", flush=True)
    FDTD, CSX, port, nf2ff, (f0, fc, f_start, f_stop) = build_model(p)
    print("TASMEEM: running openEMS (this takes a few minutes)", flush=True)
    t0 = time.time()
    FDTD.Run(sim_dir, cleanup=True)
    runtime = time.time() - t0

    return save_results(port, nf2ff, f0, fc, f_start, f_stop, p["port"]["impedance"], sim_dir, out_dir, runtime)


def save_results(port, nf2ff, f0, fc, f_start, f_stop, z0, sim_dir, out_dir, runtime=0.0):
    """S11, bandwidth and far field from a finished run. Writes results.json, S11.s1p and
    farfield.json into out_dir, which is what the app's Results and Far Field tabs read."""
    print("TASMEEM: calculating results", flush=True)
    freq = np.linspace(max(f0 - fc, 1e6), f0 + fc, 801)
    port.CalcPort(sim_dir, freq, ref_impedance=z0)
    s11 = port.uf_ref / port.uf_inc
    s11_dB = 20 * np.log10(np.abs(s11))
    zin = port.uf_tot / port.if_tot

    # the resonance is the lowest S11 inside the range the user asked for
    inside = np.where((freq >= f_start - 1e-3) & (freq <= f_stop + 1e-3))[0]
    idx = int(inside[np.argmin(s11_dB[inside])])
    f_res = freq[idx]
    at_edge = idx in (inside[0], inside[-1])
    lo = hi = idx
    while lo > 0 and s11_dB[lo - 1] < -10:
        lo -= 1
    while hi < len(freq) - 1 and s11_dB[hi + 1] < -10:
        hi += 1
    bw = [freq[lo] / 1e9, freq[hi] / 1e9] if s11_dB[idx] < -10 else None

    theta = np.arange(-180.0, 181.0, 2.0)
    phi = [0.0, 90.0]
    ff = nf2ff.CalcNF2FF(sim_dir, f_res, theta, phi, outfile="nf2ff_cuts.h5", read_cached=False)
    dmax = float(ff.Dmax[0])
    pattern = 20 * np.log10(ff.E_norm[0] / np.max(ff.E_norm[0])) + 10 * np.log10(dmax)

    res = {
        "freq_GHz": list(freq / 1e9), "s11_dB": list(s11_dB),
        "s11_re": list(np.real(s11)), "s11_im": list(np.imag(s11)),
        "zin_re": list(np.real(zin)), "zin_im": list(np.imag(zin)), "z0": z0,
        "f_res_GHz": f_res / 1e9, "s11_min_dB": float(s11_dB[idx]), "bandwidth_GHz": bw,
        "res_at_edge": bool(at_edge),
        "directivity_dBi": 10 * math.log10(dmax),
        "theta": list(theta), "pattern_phi0": list(pattern[:, 0]), "pattern_phi90": list(pattern[:, 1]),
        "runtime_s": runtime, "f_start_GHz": f_start / 1e9, "f_stop_GHz": f_stop / 1e9,
    }
    keep = (freq >= f_start) & (freq <= f_stop)        # the Touchstone file covers the user's range
    write_touchstone(os.path.join(out_dir, "S11.s1p"), freq[keep], s11[keep], z0)

    print("TASMEEM: calculating the 3D far field", flush=True)
    ffd = far_field(port, nf2ff, sim_dir, f_res, z0, out_dir, "farfield.json")
    for k in ("gain_dBi", "realized_gain_dBi", "efficiency"):
        res[k] = ffd[k]
    res["directivity_3d_dBi"] = ffd["directivity_dBi"]
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f)

    print("TASMEEM: resonance %.3f GHz, S11 %.2f dB, directivity %.2f dBi, gain %.2f dBi, efficiency %.0f%%"
          % (res["f_res_GHz"], res["s11_min_dB"], res["directivity_dBi"], res["gain_dBi"],
             100 * res["efficiency"]), flush=True)
    if bw:
        print("TASMEEM: -10 dB bandwidth %.3f to %.3f GHz" % (bw[0], bw[1]), flush=True)
    if at_edge:
        print("TASMEEM: note: the lowest S11 is at the edge of your range, so the resonance may be outside it",
              flush=True)
    print("TASMEEM: done", flush=True)
    return res


def far_field(port, nf2ff, sim_dir, f, z0, out_dir, name=None):
    """Full-sphere far field at frequency f (Hz): pattern in dBi on a theta/phi grid,
    plus directivity, gain and radiation efficiency. Written to out_dir/name."""
    port.CalcPort(sim_dir, [f], ref_impedance=z0)
    p_inc = float(np.real(port.P_inc[0]))
    p_acc = float(np.real(port.P_acc[0]))
    ff = nf2ff.CalcNF2FF(sim_dir, f, FF_THETA, FF_PHI, outfile="nf2ff_3d_%d.h5" % round(f / 1e3),
                         read_cached=False)
    dmax = float(ff.Dmax[0])
    prad = float(ff.Prad[0])
    e = np.abs(ff.E_norm[0])
    pattern = 20 * np.log10(np.maximum(e / np.max(e), 1e-6)) + 10 * np.log10(dmax)
    eff = prad / p_acc if p_acc > 0 else float("nan")
    out = {
        "f_GHz": f / 1e9, "theta": list(FF_THETA), "phi": list(FF_PHI),
        "pattern_dBi": [list(map(float, row)) for row in pattern],
        "directivity_dBi": 10 * math.log10(dmax),
        "efficiency": eff,
        "gain_dBi": 10 * math.log10(dmax * eff) if eff > 0 else float("nan"),
        "realized_gain_dBi": 10 * math.log10(dmax * prad / p_inc) if p_inc > 0 and prad > 0 else float("nan"),
        "P_rad_W": prad, "P_acc_W": p_acc, "P_inc_W": p_inc,
    }
    i, j = np.unravel_index(np.argmax(pattern), pattern.shape)
    out["max_theta"], out["max_phi"] = float(FF_THETA[i]), float(FF_PHI[j])
    name = name or "farfield_%.4fGHz.json" % (f / 1e9)
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print("TASMEEM: far field at %.4f GHz: directivity %.2f dBi, gain %.2f dBi, efficiency %.0f%%, saved %s"
          % (f / 1e9, out["directivity_dBi"], out["gain_dBi"], 100 * eff, name), flush=True)
    return out


def recalc_far_field(p, run_dir, f_GHz):
    """Far field of a finished design run at another frequency (no new simulation)."""
    FDTD, CSX, port, nf2ff, (f0, fc, f_start, f_stop) = build_model(p)
    if not f0 - fc - 1 <= f_GHz * 1e9 <= f0 + fc + 1:
        raise SystemExit("TASMEEM: %.4f GHz is outside the simulated band (%.3f to %.3f GHz)"
                         % (f_GHz, (f0 - fc) / 1e9, (f0 + fc) / 1e9))
    return far_field(port, nf2ff, os.path.join(run_dir, "sim"), f_GHz * 1e9, p["port"]["impedance"], run_dir)


def write_touchstone(path, freq, s11, z0):
    """S11 as a .s1p file, which QucsStudio / Qucs-S / KiCad can read."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("! S11 from the TASMEEM EM simulator (openEMS)\n")
        f.write("# Hz S RI R %g\n" % z0)
        for fr, s in zip(freq, s11):
            f.write("%.6e %.9f %.9f\n" % (fr, s.real, s.imag))


# ---------------------------------------------------------------- editable script

def make_script(p):
    """The same simulation as build_model + run, written out as a plain openEMS Python
    script the user can read, change and run from the app's script editor."""
    b = p["board"]
    cells, edge_res = MESH_QUALITY[p.get("mesh", "normal")]
    nrts = MAX_TIMESTEPS[p.get("mesh", "normal")]
    shapes = ",\n".join("    " + repr({k: v for k, v in s.items() if k != "hidden"}) for s in p["shapes"])
    pt = p["port"] or {"x": 0.0, "y": 0.0, "width": 2.0, "length": 10.0, "direction": "-x", "impedance": 50.0}
    return SCRIPT_TEMPLATE.format(
        name=p.get("name", "design"), date=time.strftime("%Y-%m-%d %H:%M"),
        f_start=p["freq"]["start"], f_stop=p["freq"]["stop"],
        SL=b["length"], SW=b["width"], SH=b["thickness"], epsR=b["epsR"], tanD=b["tanD"],
        ground=bool(b.get("ground", True)), airbox=list(p["airbox"]), mesh=p.get("mesh", "normal"),
        cells=cells, edge_res=edge_res, nrts=nrts, endc=repr(END_CRITERIA), shapes=shapes, port=repr(pt))


SCRIPT_TEMPLATE = """# openEMS script made by the TASMEEM EM Simulator from "{name}" ({date})
#
# Run it with Debug > Run script (F5). Whatever it saves with tasmeem.save_results()
# shows up in the Results tab. Everything here is plain openEMS Python, so you can
# change any value, add shapes, or write your own steps.

import math
import os
import sys
import time

import numpy as np
import em_engine as tasmeem          # TASMEEM helpers (load before openEMS on Windows)
from CSXCAD import ContinuousStructure
from openEMS import openEMS

args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT_DIR = os.path.abspath(args[0] if args else "script_run")
SIM_DIR = os.path.join(OUT_DIR, "sim")
os.makedirs(OUT_DIR, exist_ok=True)

# ------------------------------------------------ settings (lengths in mm)
F_START = {f_start} * 1e9            # Hz
F_STOP = {f_stop} * 1e9
F0, FC = tasmeem.excitation(F_START, F_STOP)   # test pulse (center, half width) that covers the range
SL, SW, SH = {SL}, {SW}, {SH}        # board length (x), width (y), thickness
EPS_R, TAN_D = {epsR}, {tanD}        # substrate permittivity and loss tangent
GROUND = {ground}                    # ground plane under the board
AIRBOX = {airbox}                    # simulation box size (x, y, z)
CELLS_PER_WAVELENGTH = {cells}       # "{mesh}" mesh
EDGE_RES = {edge_res}                # extra mesh resolution at metal edges
MAX_TIMESTEPS = {nrts}
END_CRITERIA = {endc}                # stop once the energy has fallen this far (1e-4 = -40 dB)

# ------------------------------------------------ solver
FDTD = openEMS(NrTS=MAX_TIMESTEPS, EndCriteria=END_CRITERIA)
FDTD.SetGaussExcite(F0, FC)
FDTD.SetBoundaryCond(["MUR"] * 6)

CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(1e-3)              # all lengths in mm
mesh.AddLine("x", [-AIRBOX[0] / 2, AIRBOX[0] / 2])
mesh.AddLine("y", [-AIRBOX[1] / 2, AIRBOX[1] / 2])
mesh.AddLine("z", [-AIRBOX[2] / 3, AIRBOX[2] * 2 / 3])

# ------------------------------------------------ substrate and ground plane
kappa = TAN_D * 2 * math.pi * F0 * tasmeem.EPS0 * EPS_R
substrate = CSX.AddMaterial("substrate", epsilon=EPS_R, kappa=kappa)
substrate.AddBox([-SL / 2, -SW / 2, 0], [SL / 2, SW / 2, SH], priority=0)
mesh.AddLine("z", np.linspace(0, SH, 5))     # 4 cells through the substrate
FDTD.AddEdges2Grid(dirs="xy", properties=substrate)

if GROUND:
    gnd = CSX.AddMetal("gnd")
    gnd.AddBox([-SL / 2, -SW / 2, 0], [SL / 2, SW / 2, 0], priority=10)

# ------------------------------------------------ top copper
# rectangle: x, y = center, length along x, width along y
# taper:     start, end, center, width1, width2, axis "x" or "y"
# arc:       x, y = center, r_inner, r_outer, angle_start, angle_stop (degrees)
SHAPES = [
{shapes}
]

metal = CSX.AddMetal("metal")
for s in SHAPES:
    xs, ys = tasmeem.shape_outline(s)
    if s["type"] == "rectangle":
        box = metal.AddBox([min(xs), min(ys), SH], [max(xs), max(ys), SH], priority=10)
        FDTD.AddEdges2Grid(dirs="xy", primitives=box, metal_edge_res=EDGE_RES)
        mesh.AddLine("x", [min(xs), max(xs)])
        mesh.AddLine("y", [min(ys), max(ys)])
    else:
        metal.AddPolygon([xs, ys], "z", SH, priority=10)
        lx, ly = tasmeem.polygon_mesh_lines(xs, ys, EDGE_RES)
        mesh.AddLine("x", lx)
        mesh.AddLine("y", ly)

# ------------------------------------------------ port (microstrip)
PORT = {port}
sign = -1 if PORT["direction"].startswith("-") else 1
axis = PORT["direction"][1]
if axis == "x":
    start = [PORT["x"], PORT["y"] - PORT["width"] / 2, SH]
    stop = [PORT["x"] + sign * PORT["length"], PORT["y"] + PORT["width"] / 2, 0]
    mesh.AddLine("y", np.linspace(start[1], stop[1], 5))
    mesh.AddLine("x", [start[0], stop[0]])
else:
    start = [PORT["x"] - PORT["width"] / 2, PORT["y"], SH]
    stop = [PORT["x"] + PORT["width"] / 2, PORT["y"] + sign * PORT["length"], 0]
    mesh.AddLine("x", np.linspace(start[0], stop[0], 5))
    mesh.AddLine("y", [start[1], stop[1]])

# ------------------------------------------------ mesh, port, far-field box
tasmeem.finish_mesh(mesh, F0, FC, CELLS_PER_WAVELENGTH, EDGE_RES)
port = FDTD.AddMSLPort(1, metal, start, stop, axis, "z", excite=1, FeedShift=2,
                       MeasPlaneShift=PORT["length"] / 2, priority=999)
nf2ff = FDTD.CreateNF2FFBox()

if "--setup-only" in sys.argv:       # used by Debug > Show script model in AppCSXCAD
    CSX.Write2XML(os.path.join(OUT_DIR, "model.xml"))
    print(os.path.join(OUT_DIR, "model.xml"))
    sys.exit(0)

far = [a for a in sys.argv if a.startswith("--farfield=")]
if far:                              # used by the Far Field tab: recalculate at another frequency, no new run
    tasmeem.far_field(port, nf2ff, SIM_DIR, float(far[0].split("=")[1]) * 1e9, PORT["impedance"], OUT_DIR)
    sys.exit(0)

# ------------------------------------------------ run and save results
print("TASMEEM: running openEMS (this takes a few minutes)", flush=True)
t0 = time.time()
FDTD.Run(SIM_DIR, cleanup=True)
tasmeem.save_results(port, nf2ff, F0, FC, F_START, F_STOP, PORT["impedance"], SIM_DIR, OUT_DIR,
                     time.time() - t0)
"""


if __name__ == "__main__":
    if sys.argv[1:2] == ["farfield"] and len(sys.argv) == 5:
        with open(sys.argv[2], encoding="utf-8-sig") as f:
            project = clean_project(json.load(f))[0]
        recalc_far_field(project, sys.argv[3], float(sys.argv[4]))
        sys.exit(0)
    if len(sys.argv) != 4 or sys.argv[1] not in ("run", "export", "script"):
        print("usage: em_engine.py run|export|script project.json output  or  farfield project.json run_dir f_GHz")
        sys.exit(1)
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        project, problem = clean_project(json.load(f))
    if problem:
        print("TASMEEM: this is not a valid design: " + problem)
        sys.exit(1)
    if sys.argv[1] == "run":
        run(project, sys.argv[3])
    elif sys.argv[1] == "script":
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            f.write(make_script(project))
    else:
        print(export_model(project, sys.argv[3]))
