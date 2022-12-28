"""Configuration file parser."""


from copy import deepcopy

import yaml

from src.simulator.actions import get_action
from src.simulator.bom import BOM
from src.simulator.consumable import Consumable
from src.simulator.containers import (
    ConsumableContainer,
    MaterialContainer,
    ProductContainer,
)
from src.simulator.machine import Machine
from src.simulator.maintenance import Maintenance
from src.simulator.material import Material
from src.simulator.operator import Operator
from src.simulator.product import Product
from src.simulator.program import Program
from src.simulator.schedules import CronBlock, OperatingSchedule
from src.simulator.sensors import get_sensor_by_type


def cfg2obj(env, obj, cfg_list):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        out[id_] = obj(env, **cfg)

    return out


def make_boms(env, cfg_list, material_objs, consumable_objs, product_objs):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")

        # Materials
        materials_ = {}
        for material in cfg.pop("materials", {}):
            obj = material_objs[material["id"]]
            # TODO: Consume time as well?
            consumption = float(material["consumption"]) / 60 / 60
            materials_[obj] = {"consumption": consumption}

        # Consumables
        consumables_ = {}
        for consumable in cfg.pop("consumables", {}):
            obj = consumable_objs[consumable["id"]]
            consumption = float(consumable["consumption"]) / 60 / 60
            consumables_[obj] = {"consumption": consumption}

        # Products (output)
        products_ = {}
        for product in cfg.pop("products", {}):
            obj = product_objs[product["id"]]
            quantity = float(product["quantity"])
            products_[obj] = {"quantity": quantity}

        out[id_] = BOM(
            env,
            **cfg,
            materials=materials_,
            consumables=consumables_,
            products=products_,
        )

    return out


def make_programs(env, cfg_list, boms):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        bom_ = boms[cfg.pop("bom")]
        out[id_] = Program(id_, env, bom=bom_, **cfg)

    return out


def make_schedules(env, cfg_list, programs):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        blocks_ = []
        for block in cfg.pop("blocks", []):
            block_cfg = {}
            assert "cron" in block, 'Only "cron" blocks supported'
            # Generic
            for kwarg in ["cron", "name", "duration-hours", "priority"]:
                if kwarg in block:
                    block_cfg[kwarg.replace("-", "_")] = block[kwarg]

            # Action as a separate animal
            action = block["action"]
            action_name = action["name"]
            action_args = action.get("args", ())
            action_kwargs = action.get("kwargs", {})
            action = get_action(action_name, *action_args, **action_kwargs)

            block_obj = CronBlock(env, action=action, **block_cfg)
            blocks_.append(block_obj)
        out[id_] = OperatingSchedule(env, blocks=blocks_, **cfg)

    return out


def make_machines(env, cfg_list, containers, programs, schedules, maintenance):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        d = {}
        id_ = cfg.pop("id")
        if "name" in cfg:
            d["name"] = cfg["name"]
        if "containers" in cfg:
            d["containers"] = [containers[cid] for cid in cfg["containers"]]
        if "programs" in cfg:
            d["programs"] = [programs[pid] for pid in cfg["programs"]]
        if "schedule" in cfg:
            d["schedule"] = schedules[cfg["schedule"]]
        if "default-program" in cfg:
            d["default_program"] = programs[cfg["default-program"]]
        if "maintenance" in cfg:
            d["maintenance"] = maintenance[cfg["maintenance"]]

        out[id_] = Machine(env, **d)

    return out


def make_maintenance(env, cfg_list):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        out[id_] = Maintenance(env, **cfg)
    return out


def make_containers(env, cfg_list, materials, consumables, products):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        content_id = cfg.pop("content")
        if content_id in materials:
            material = materials[content_id]
            out[id_] = MaterialContainer(env, material, **cfg)
        elif content_id in consumables:
            consumable = consumables[content_id]
            out[id_] = ConsumableContainer(env, consumable, **cfg)
        elif content_id in products:
            product = products[content_id]
            out[id_] = ProductContainer(env, product, **cfg)

    return out


def make_operators(env, cfg_list, machines):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        op = {}
        if "machine" in cfg:
            op["machine"] = machines[cfg["machine"]]
        if "name" in cfg:
            op["name"] = cfg["name"]
        out[id_] = Operator(env, **op)

    return out


def make_sensors(env, cfg_list):
    cfg_list = deepcopy(cfg_list)
    out = {}
    for cfg in cfg_list:
        id_ = cfg.pop("id")
        sensor_type = cfg.pop("type")
        kwargs = cfg.get("kwargs") or {}
        cls = get_sensor_by_type(sensor_type)
        out[id_] = cls(env, **kwargs)

    return out


def parse_config(env, path: str):
    """Parse factory configuration file."""
    # Read YAML
    with open(path, "r") as f:
        cfg = yaml.full_load(f.read())

    # Create objects
    materials = cfg2obj(env, Material, cfg["materials"])
    consumables = cfg2obj(env, Consumable, cfg["consumables"])
    products = cfg2obj(env, Product, cfg["products"])
    containers = make_containers(
        env, cfg["containers"], materials, consumables, products
    )
    boms = make_boms(env, cfg["boms"], materials, consumables, products)
    maintenance = make_maintenance(env, cfg["maintenance"])
    programs = make_programs(env, cfg["programs"], boms)
    schedules = make_schedules(env, cfg["schedules"], programs)
    machines = make_machines(
        env, cfg["machines"], containers, programs, schedules, maintenance
    )
    operators = make_operators(env, cfg["operators"], machines)
    sensors = make_sensors(env, cfg["sensors"])

    # Output only when dictionary is not empty
    out = {
        "materials": materials,
        "consumables": consumables,
        "products": products,
        "containers": containers,
        "boms": boms,
        "maintenance": maintenance,
        "programs": programs,
        "schedules": schedules,
        "machines": machines,
        "operators": operators,
        "sensors": sensors,
    }
    if "name" in cfg:
        out["name"] = cfg["name"]
    if "id" in cfg:
        out["uid"] = cfg["id"]

    return out
