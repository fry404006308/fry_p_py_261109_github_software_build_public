"""Read a finished RIP workbench smoke job. Runs on the CI Python using only its standard library."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

GOLDEN_MD5 = "a1933e99be27da3f2c2f36a7cd35341e"
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
VIEWS = ("front", "back", "left", "right", "top", "bottom")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def single(root, pattern):
    matches = list(root.rglob(pattern))
    assert len(matches) == 1, (root, pattern, matches)
    return matches[0]


def check_stack(root, engine):
    metadata_file = single(root, "slice_metadata.json")
    md = read_json(metadata_file)
    folder = metadata_file.parent
    assert md["engine_str"] == engine, md
    if engine == "cpp":
        assert md["sdk_version_str"] == "0.4.0"
        assert md["params_dict"]["orient_mode"] == "original"
    orientation = read_json(folder / "_orient.json")
    assert orientation["glb_to_voxel_matrix"] == IDENTITY
    files = sorted(folder.glob("*.bmp"))
    assert len(files) == md["slice_count_int"] == 309
    digest = hashlib.md5()
    for layer, file in enumerate(files):
        assert file.name == f"{layer:06d}.bmp", file
        raw = file.read_bytes()
        assert raw[:2] == b"BM" and struct.unpack_from("<H", raw, 28)[0] == 4
        digest.update(raw)
    assert digest.hexdigest() == md["bmp_md5_str"] == GOLDEN_MD5
    assert md["inked_voxel_int"] == 76758
    return {"slices":len(files), "md5":digest.hexdigest(), "engine":engine}


def check_png(file):
    raw = file.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", file
    offset = 8
    compressed = bytearray()
    width = height = 0
    while offset < len(raw):
        size, kind = struct.unpack_from(">I4s", raw, offset)
        data = raw[offset + 8:offset + size + 8]
        crc, = struct.unpack_from(">I", raw, offset + size + 8)
        assert zlib.crc32(kind + data) == crc
        if kind == b"IHDR":
            width, height = struct.unpack_from(">II", data)
        if kind == b"IDAT":
            compressed.extend(data)
        offset += size + 12
        if kind == b"IEND":
            break
    assert width > 0 and height > 0 and zlib.decompress(compressed)
    return [width, height]


def check_sim(folder):
    views = {name: check_png(single(folder, f"view_{name}.png")) for name in VIEWS}
    raw = single(folder, "*.glb").read_bytes()
    assert struct.unpack_from("<4sII", raw) == (b"glTF", 2, len(raw))
    length, kind = struct.unpack_from("<I4s", raw, 12)
    assert kind == b"JSON"
    doc = json.loads(raw[20:20 + length])
    positions = [doc["accessors"][p["attributes"]["POSITION"]]["count"]
                 for mesh in doc["meshes"] for p in mesh["primitives"]]
    assert positions and min(positions) > 0
    effective = read_json(single(folder, "result.json"))["key_output_dict"]
    engines = [v["sim_engine_str"] for v in effective.values()
               if isinstance(v, dict) and "sim_engine_str" in v]
    assert len(engines) >= 2 and all(v.startswith("dll") and "整条流程" in v for v in engines), engines
    return {"views":views, "vertices":sum(positions), "engines":engines}


def main(folder, version):
    gui = read_json(folder / "gui/gui.json")
    assert gui["software"]["version_str"] == version and gui["title"].endswith(version)
    assert len(gui["features"]) >= 14 and gui["io_switch_check"]
    data = {"version":version, "features":len(gui["features"]),
            "python":check_stack(folder / "out_python", "python"),
            "cpp":check_stack(folder / "out_dll", "cpp"),
            "simulation":check_sim(folder / "out_sim")}
    (folder / "release_acceptance.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
    print("RIP_ACCEPTANCE", json.dumps(data, ensure_ascii=True))


if __name__ == "__main__":
    manifest = Path(sys.argv[2])
    version = read_json(manifest)["version_str"] if manifest.is_file() else sys.argv[2]
    main(Path(sys.argv[1]), version)
