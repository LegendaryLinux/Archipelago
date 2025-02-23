import argparse
import logging
import random
import urllib.request
import urllib.parse
import typing
import os
from collections import Counter
import string

import ModuleUpdate

ModuleUpdate.update()

import Utils
from worlds.alttp import Options as LttPOptions
from worlds.generic import PlandoConnection
from Utils import parse_yaml, version_tuple, __version__, tuplize_version, get_options, local_path, user_path
from worlds.alttp.EntranceRandomizer import parse_arguments
from Main import main as ERmain
from BaseClasses import seeddigits, get_seed
import Options
from worlds.alttp import Bosses
from worlds.alttp.Text import TextTable
from worlds.AutoWorld import AutoWorldRegister
import copy

categories = set(AutoWorldRegister.world_types)


def mystery_argparse():
    options = get_options()
    defaults = options["generator"]

    def resolve_path(path: str, resolver: typing.Callable[[str], str]) -> str:
        return path if os.path.isabs(path) else resolver(path)

    parser = argparse.ArgumentParser(description="CMD Generation Interface, defaults come from host.yaml.")
    parser.add_argument('--weights_file_path', default=defaults["weights_file_path"],
                        help='Path to the weights file to use for rolling game settings, urls are also valid')
    parser.add_argument('--samesettings', help='Rolls settings per weights file rather than per player',
                        action='store_true')
    parser.add_argument('--player_files_path', default=resolve_path(defaults["player_files_path"], user_path),
                        help="Input directory for player files.")
    parser.add_argument('--seed', help='Define seed number to generate.', type=int)
    parser.add_argument('--multi', default=defaults["players"], type=lambda value: max(int(value), 1))
    parser.add_argument('--spoiler', type=int, default=defaults["spoiler"])
    parser.add_argument('--lttp_rom', default=options["lttp_options"]["rom_file"],
                        help="Path to the 1.0 JP LttP Baserom.")  # absolute, relative to cwd or relative to app path
    parser.add_argument('--sm_rom', default=options["sm_options"]["rom_file"],
                        help="Path to the 1.0 JP SM Baserom.")
    parser.add_argument('--enemizercli', default=resolve_path(defaults["enemizer_path"], local_path))
    parser.add_argument('--outputpath', default=resolve_path(options["general_options"]["output_path"], user_path),
                        help="Path to output folder. Absolute or relative to cwd.")  # absolute or relative to cwd
    parser.add_argument('--race', action='store_true', default=defaults["race"])
    parser.add_argument('--meta_file_path', default=defaults["meta_file_path"])
    parser.add_argument('--log_level', default='info', help='Sets log level')
    parser.add_argument('--yaml_output', default=0, type=lambda value: max(int(value), 0),
                        help='Output rolled mystery results to yaml up to specified number (made for async multiworld)')
    parser.add_argument('--plando', default=defaults["plando_options"],
                        help='List of options that can be set manually. Can be combined, for example "bosses, items"')
    args = parser.parse_args()
    if not os.path.isabs(args.weights_file_path):
        args.weights_file_path = os.path.join(args.player_files_path, args.weights_file_path)
    if not os.path.isabs(args.meta_file_path):
        args.meta_file_path = os.path.join(args.player_files_path, args.meta_file_path)
    args.plando: typing.Set[str] = {arg.strip().lower() for arg in args.plando.split(",")}
    return args, options


def get_seed_name(random_source) -> str:
    return f"{random_source.randint(0, pow(10, seeddigits) - 1)}".zfill(seeddigits)


def main(args=None, callback=ERmain):
    if not args:
        args, options = mystery_argparse()

    seed = get_seed(args.seed)
    random.seed(seed)
    seed_name = get_seed_name(random)

    if args.race:
        random.seed()  # reset to time-based random source

    weights_cache = {}
    if args.weights_file_path and os.path.exists(args.weights_file_path):
        try:
            weights_cache[args.weights_file_path] = read_weights_yaml(args.weights_file_path)
        except Exception as e:
            raise ValueError(f"File {args.weights_file_path} is destroyed. Please fix your yaml.") from e
        print(f"Weights: {args.weights_file_path} >> "
              f"{get_choice('description', weights_cache[args.weights_file_path], 'No description specified')}")

    if args.meta_file_path and os.path.exists(args.meta_file_path):
        try:
            weights_cache[args.meta_file_path] = read_weights_yaml(args.meta_file_path)
        except Exception as e:
            raise ValueError(f"File {args.meta_file_path} is destroyed. Please fix your yaml.") from e
        meta_weights = weights_cache[args.meta_file_path]
        print(f"Meta: {args.meta_file_path} >> {get_choice('meta_description', meta_weights)}")
        del(meta_weights["meta_description"])
        if args.samesettings:
            raise Exception("Cannot mix --samesettings with --meta")
    else:
        meta_weights = None
    player_id = 1
    player_files = {}
    for file in os.scandir(args.player_files_path):
        fname = file.name
        if file.is_file() and os.path.join(args.player_files_path, fname) not in {args.meta_file_path, args.weights_file_path}:
            path = os.path.join(args.player_files_path, fname)
            try:
                weights_cache[fname] = read_weights_yaml(path)
            except Exception as e:
                raise ValueError(f"File {fname} is destroyed. Please fix your yaml.") from e
            else:
                print(f"P{player_id} Weights: {fname} >> "
                      f"{get_choice('description', weights_cache[fname], 'No description specified')}")
                player_files[player_id] = fname
                player_id += 1

    args.multi = max(player_id-1, args.multi)
    print(f"Generating for {args.multi} player{'s' if args.multi > 1 else ''}, {seed_name} Seed {seed} with plando: "
          f"{', '.join(args.plando)}")

    if not weights_cache:
        raise Exception(f"No weights found. Provide a general weights file ({args.weights_file_path}) or individual player files. "
                        f"A mix is also permitted.")
    erargs = parse_arguments(['--multi', str(args.multi)])
    erargs.seed = seed
    erargs.glitch_triforce = options["generator"]["glitch_triforce_room"]
    erargs.spoiler = args.spoiler
    erargs.race = args.race
    erargs.outputname = seed_name
    erargs.outputpath = args.outputpath

    Utils.init_logging(f"Generate_{seed}", loglevel=args.log_level)

    erargs.lttp_rom = args.lttp_rom
    erargs.sm_rom = args.sm_rom
    erargs.enemizercli = args.enemizercli

    settings_cache = {k: (roll_settings(v, args.plando) if args.samesettings else None)
                      for k, v in weights_cache.items()}
    player_path_cache = {}
    for player in range(1, args.multi + 1):
        player_path_cache[player] = player_files.get(player, args.weights_file_path)

    if meta_weights:
        for category_name, category_dict in meta_weights.items():
            for key in category_dict:
                option = get_choice(key, category_dict)
                if option is not None:
                    for player, path in player_path_cache.items():
                        if category_name is None:
                            weights_cache[path][key] = option
                        elif category_name not in weights_cache[path]:
                            logging.warning(f"Meta: Category {category_name} is not present in {path}.")
                        else:
                            weights_cache[path][category_name][key] = option

    name_counter = Counter()
    erargs.player_settings = {}
    for player in range(1, args.multi + 1):
        path = player_path_cache[player]
        if path:
            try:
                settings = settings_cache[path] if settings_cache[path] else \
                    roll_settings(weights_cache[path], args.plando)
                for k, v in vars(settings).items():
                    if v is not None:
                        try:
                            getattr(erargs, k)[player] = v
                        except AttributeError:
                            setattr(erargs, k, {player: v})
                        except Exception as e:
                            raise Exception(f"Error setting {k} to {v} for player {player}") from e
            except Exception as e:
                raise ValueError(f"File {path} is destroyed. Please fix your yaml.") from e
        else:
            raise RuntimeError(f'No weights specified for player {player}')
        if path == args.weights_file_path:  # if name came from the weights file, just use base player name
            erargs.name[player] = f"Player{player}"
        elif not erargs.name[player]:  # if name was not specified, generate it from filename
            erargs.name[player] = os.path.splitext(os.path.split(path)[-1])[0]
        erargs.name[player] = handle_name(erargs.name[player], player, name_counter)

    if len(set(erargs.name.values())) != len(erargs.name):
        raise Exception(f"Names have to be unique. Names: {Counter(erargs.name.values())}")

    if args.yaml_output:
        import yaml
        important = {}
        for option, player_settings in vars(erargs).items():
            if type(player_settings) == dict:
                if all(type(value) != list for value in player_settings.values()):
                    if len(player_settings.values()) > 1:
                        important[option] = {player: value for player, value in player_settings.items() if
                                             player <= args.yaml_output}
                    else:
                        logging.debug(f"No player settings defined for option '{option}'")

            else:
                if player_settings != "":  # is not empty name
                    important[option] = player_settings
                else:
                    logging.debug(f"No player settings defined for option '{option}'")
        if args.outputpath:
            os.makedirs(args.outputpath, exist_ok=True)
        with open(os.path.join(args.outputpath if args.outputpath else ".", f"generate_{seed_name}.yaml"), "wt") as f:
            yaml.dump(important, f)

    callback(erargs, seed)


def read_weights_yaml(path):
    try:
        if urllib.parse.urlparse(path).scheme in ('https', 'file'):
            yaml = str(urllib.request.urlopen(path).read(), "utf-8")
        else:
            with open(path, 'rb') as f:
                yaml = str(f.read(), "utf-8")
    except Exception as e:
        raise Exception(f"Failed to read weights ({path})") from e

    return parse_yaml(yaml)


def interpret_on_off(value) -> bool:
    return {"on": True, "off": False}.get(value, value)


def convert_to_on_off(value) -> str:
    return {True: "on", False: "off"}.get(value, value)


def get_choice_legacy(option, root, value=None) -> typing.Any:
    if option not in root:
        return value
    if type(root[option]) is list:
        return interpret_on_off(random.choices(root[option])[0])
    if type(root[option]) is not dict:
        return interpret_on_off(root[option])
    if not root[option]:
        return value
    if any(root[option].values()):
        return interpret_on_off(
            random.choices(list(root[option].keys()), weights=list(map(int, root[option].values())))[0])
    raise RuntimeError(f"All options specified in \"{option}\" are weighted as zero.")


def get_choice(option, root, value=None) -> typing.Any:
    if option not in root:
        return value
    if type(root[option]) is list:
        return random.choices(root[option])[0]
    if type(root[option]) is not dict:
        return root[option]
    if not root[option]:
        return value
    if any(root[option].values()):
        return random.choices(list(root[option].keys()), weights=list(map(int, root[option].values())))[0]
    raise RuntimeError(f"All options specified in \"{option}\" are weighted as zero.")


class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def handle_name(name: str, player: int, name_counter: Counter):
    name_counter[name] += 1
    new_name = "%".join([x.replace("%number%", "{number}").replace("%player%", "{player}") for x in name.split("%%")])
    new_name = string.Formatter().vformat(new_name, (), SafeDict(number=name_counter[name],
                                                                 NUMBER=(name_counter[name] if name_counter[
                                                                                                   name] > 1 else ''),
                                                                 player=player,
                                                                 PLAYER=(player if player > 1 else '')))
    new_name = new_name.strip()[:16]
    if new_name == "Archipelago":
        raise Exception(f"You cannot name yourself \"{new_name}\"")
    return new_name


def prefer_int(input_data: str) -> typing.Union[str, int]:
    try:
        return int(input_data)
    except:
        return input_data


available_boss_names: typing.Set[str] = {boss.lower() for boss in Bosses.boss_table if boss not in
                                         {'Agahnim', 'Agahnim2', 'Ganon'}}
available_boss_locations: typing.Set[str] = {f"{loc.lower()}{f' {level}' if level else ''}" for loc, level in
                                             Bosses.boss_location_table}

boss_shuffle_options = {None: 'none',
                        'none': 'none',
                        'basic': 'basic',
                        'full': 'full',
                        'chaos': 'chaos',
                        'singularity': 'singularity'
                        }

goals = {
    'ganon': 'ganon',
    'crystals': 'crystals',
    'bosses': 'bosses',
    'pedestal': 'pedestal',
    'ganon_pedestal': 'ganonpedestal',
    'triforce_hunt': 'triforcehunt',
    'local_triforce_hunt': 'localtriforcehunt',
    'ganon_triforce_hunt': 'ganontriforcehunt',
    'local_ganon_triforce_hunt': 'localganontriforcehunt',
    'ice_rod_hunt': 'icerodhunt',
}


def roll_percentage(percentage: typing.Union[int, float]) -> bool:
    """Roll a percentage chance.
    percentage is expected to be in range [0, 100]"""
    return random.random() < (float(percentage) / 100)


def update_weights(weights: dict, new_weights: dict, type: str, name: str) -> dict:
    logging.debug(f'Applying {new_weights}')
    new_options = set(new_weights) - set(weights)
    weights.update(new_weights)
    if new_options:
        for new_option in new_options:
            logging.warning(f'{type} Suboption "{new_option}" of "{name}" did not '
                            f'overwrite a root option. '
                            f'This is probably in error.')
    return weights


def roll_linked_options(weights: dict) -> dict:
    weights = copy.deepcopy(weights)  # make sure we don't write back to other weights sets in same_settings
    for option_set in weights["linked_options"]:
        if "name" not in option_set:
            raise ValueError("One of your linked options does not have a name.")
        try:
            if roll_percentage(option_set["percentage"]):
                logging.debug(f"Linked option {option_set['name']} triggered.")
                new_options = option_set["options"]
                for category_name, category_options in new_options.items():
                    currently_targeted_weights = weights
                    if category_name:
                        currently_targeted_weights = currently_targeted_weights[category_name]
                    update_weights(currently_targeted_weights, category_options, "Linked", option_set["name"])
            else:
                logging.debug(f"linked option {option_set['name']} skipped.")
        except Exception as e:
            raise ValueError(f"Linked option {option_set['name']} is destroyed. "
                             f"Please fix your linked option.") from e
    return weights


def roll_triggers(weights: dict, triggers: list) -> dict:
    weights = copy.deepcopy(weights)  # make sure we don't write back to other weights sets in same_settings
    weights["_Generator_Version"] = Utils.__version__
    for i, option_set in enumerate(triggers):
        try:
            currently_targeted_weights = weights
            category = option_set.get("option_category", None)
            if category:
                currently_targeted_weights = currently_targeted_weights[category]
            key = get_choice("option_name", option_set)
            if key not in currently_targeted_weights:
                logging.warning(f'Specified option name {option_set["option_name"]} did not '
                                f'match with a root option. '
                                f'This is probably in error.')
            trigger_result = get_choice("option_result", option_set)
            result = get_choice(key, currently_targeted_weights)
            currently_targeted_weights[key] = result
            if result == trigger_result and roll_percentage(get_choice("percentage", option_set, 100)):
                for category_name, category_options in option_set["options"].items():
                    currently_targeted_weights = weights
                    if category_name:
                        currently_targeted_weights = currently_targeted_weights[category_name]
                    update_weights(currently_targeted_weights, category_options, "Triggered", option_set["option_name"])

        except Exception as e:
            raise ValueError(f"Your trigger number {i + 1} is destroyed. "
                             f"Please fix your triggers.") from e
    return weights


def get_plando_bosses(boss_shuffle: str, plando_options: typing.Set[str]) -> str:
    if boss_shuffle in boss_shuffle_options:
        return boss_shuffle_options[boss_shuffle]
    elif "bosses" in plando_options:
        options = boss_shuffle.lower().split(";")
        remainder_shuffle = "none"  # vanilla
        bosses = []
        for boss in options:
            if boss in boss_shuffle_options:
                remainder_shuffle = boss_shuffle_options[boss]
            elif "-" in boss:
                loc, boss_name = boss.split("-")
                if boss_name not in available_boss_names:
                    raise ValueError(f"Unknown Boss name {boss_name}")
                if loc not in available_boss_locations:
                    raise ValueError(f"Unknown Boss Location {loc}")
                level = ''
                if loc.split(" ")[-1] in {"top", "middle", "bottom"}:
                    # split off level
                    loc = loc.split(" ")
                    level = f" {loc[-1]}"
                    loc = " ".join(loc[:-1])
                loc = loc.title().replace("Of", "of")
                if not Bosses.can_place_boss(boss_name.title(), loc, level):
                    raise ValueError(f"Cannot place {boss_name} at {loc}{level}")
                bosses.append(boss)
            elif boss not in available_boss_names:
                raise ValueError(f"Unknown Boss name or Boss shuffle option {boss}.")
            else:
                bosses.append(boss)
        return ";".join(bosses + [remainder_shuffle])
    else:
        raise Exception(f"Boss Shuffle {boss_shuffle} is unknown and boss plando is turned off.")


def handle_option(ret: argparse.Namespace, game_weights: dict, option_key: str, option: type(Options.Option)):
    if option_key in game_weights:
        try:
            if not option.supports_weighting:
                player_option = option.from_any(game_weights[option_key])
            else:
                player_option = option.from_any(get_choice(option_key, game_weights))
            setattr(ret, option_key, player_option)
        except Exception as e:
            raise Exception(f"Error generating option {option_key} in {ret.game}") from e
        else:
            if hasattr(player_option, "verify"):
                player_option.verify(AutoWorldRegister.world_types[ret.game])
    else:
        setattr(ret, option_key, option(option.default))


def roll_settings(weights: dict, plando_options: typing.Set[str] = frozenset(("bosses",))):
    if "linked_options" in weights:
        weights = roll_linked_options(weights)

    if "triggers" in weights:
        weights = roll_triggers(weights, weights["triggers"])

    requirements = weights.get("requires", {})
    if requirements:
        version = requirements.get("version", __version__)
        if tuplize_version(version) > version_tuple:
            raise Exception(f"Settings reports required version of generator is at least {version}, "
                            f"however generator is of version {__version__}")
        required_plando_options = requirements.get("plando", "")
        if required_plando_options:
            required_plando_options = set(option.strip() for option in required_plando_options.split(","))
            required_plando_options -= plando_options
            if required_plando_options:
                if len(required_plando_options) == 1:
                    raise Exception(f"Settings reports required plando module {', '.join(required_plando_options)}, "
                                    f"which is not enabled.")
                else:
                    raise Exception(f"Settings reports required plando modules {', '.join(required_plando_options)}, "
                                    f"which are not enabled.")

    ret = argparse.Namespace()
    for option_key in Options.per_game_common_options:
        if option_key in weights and option_key not in Options.common_options:
            raise Exception(f"Option {option_key} has to be in a game's section, not on its own.")

    ret.game = get_choice("game", weights)
    if ret.game not in weights:
        raise Exception(f"No game options for selected game \"{ret.game}\" found.")

    world_type = AutoWorldRegister.world_types[ret.game]
    game_weights = weights[ret.game]

    if "triggers" in game_weights:
        weights = roll_triggers(weights, game_weights["triggers"])
        game_weights = weights[ret.game]

    ret.name = get_choice('name', weights)
    for option_key, option in Options.common_options.items():
        setattr(ret, option_key, option.from_any(get_choice(option_key, weights, option.default)))

    if ret.game in AutoWorldRegister.world_types:
        for option_key, option in world_type.options.items():
            handle_option(ret, game_weights, option_key, option)
        for option_key, option in Options.per_game_common_options.items():
            # skip setting this option if already set from common_options, defaulting to root option
            if not (option_key in Options.common_options and option_key not in game_weights):
                handle_option(ret, game_weights, option_key, option)
        if "items" in plando_options:
            ret.plando_items = game_weights.get("plando_items", [])
        if ret.game == "Minecraft" or ret.game == "Ocarina of Time":
            # bad hardcoded behavior to make this work for now
            ret.plando_connections = []
            if "connections" in plando_options:
                options = game_weights.get("plando_connections", [])
                for placement in options:
                    if roll_percentage(get_choice("percentage", placement, 100)):
                        ret.plando_connections.append(PlandoConnection(
                            get_choice("entrance", placement),
                            get_choice("exit", placement),
                            get_choice("direction", placement)
                        ))
        elif ret.game == "A Link to the Past":
            roll_alttp_settings(ret, game_weights, plando_options)
    else:
        raise Exception(f"Unsupported game {ret.game}")

    return ret


def roll_alttp_settings(ret: argparse.Namespace, weights, plando_options):
    if "dungeon_items" in weights and get_choice_legacy('dungeon_items', weights, "none") != "none":
        raise Exception(f"dungeon_items key in A Link to the Past was removed, but is present in these weights as {get_choice_legacy('dungeon_items', weights, False)}.")
    glitches_required = get_choice_legacy('glitches_required', weights)
    if glitches_required not in [None, 'none', 'no_logic', 'overworld_glitches', 'hybrid_major_glitches', 'minor_glitches']:
        logging.warning("Only NMG, OWG, HMG and No Logic supported")
        glitches_required = 'none'
    ret.logic = {None: 'noglitches', 'none': 'noglitches', 'no_logic': 'nologic', 'overworld_glitches': 'owglitches',
                 'minor_glitches': 'minorglitches', 'hybrid_major_glitches': 'hybridglitches'}[
        glitches_required]

    ret.dark_room_logic = get_choice_legacy("dark_room_logic", weights, "lamp")
    if not ret.dark_room_logic:  # None/False
        ret.dark_room_logic = "none"
    if ret.dark_room_logic == "sconces":
        ret.dark_room_logic = "torches"
    if ret.dark_room_logic not in {"lamp", "torches", "none"}:
        raise ValueError(f"Unknown Dark Room Logic: \"{ret.dark_room_logic}\"")

    entrance_shuffle = get_choice_legacy('entrance_shuffle', weights, 'vanilla')
    if entrance_shuffle.startswith('none-'):
        ret.shuffle = 'vanilla'
    else:
        ret.shuffle = entrance_shuffle if entrance_shuffle != 'none' else 'vanilla'

    goal = get_choice_legacy('goals', weights, 'ganon')

    ret.goal = goals[goal]

    # TODO consider moving open_pyramid to an automatic variable in the core roller, set to True when
    # fast ganon + ganon at hole
    ret.open_pyramid = get_choice_legacy('open_pyramid', weights, 'goal')

    extra_pieces = get_choice_legacy('triforce_pieces_mode', weights, 'available')

    ret.triforce_pieces_required = LttPOptions.TriforcePieces.from_any(get_choice_legacy('triforce_pieces_required', weights, 20))

    # sum a percentage to required
    if extra_pieces == 'percentage':
        percentage = max(100, float(get_choice_legacy('triforce_pieces_percentage', weights, 150))) / 100
        ret.triforce_pieces_available = int(round(ret.triforce_pieces_required * percentage, 0))
    # vanilla mode (specify how many pieces are)
    elif extra_pieces == 'available':
        ret.triforce_pieces_available = LttPOptions.TriforcePieces.from_any(
            get_choice_legacy('triforce_pieces_available', weights, 30))
    # required pieces + fixed extra
    elif extra_pieces == 'extra':
        extra_pieces = max(0, int(get_choice_legacy('triforce_pieces_extra', weights, 10)))
        ret.triforce_pieces_available = ret.triforce_pieces_required + extra_pieces

    # change minimum to required pieces to avoid problems
    ret.triforce_pieces_available = min(max(ret.triforce_pieces_required, int(ret.triforce_pieces_available)), 90)

    ret.shop_shuffle = get_choice_legacy('shop_shuffle', weights, '')
    if not ret.shop_shuffle:
        ret.shop_shuffle = ''

    ret.mode = get_choice_legacy("mode", weights)

    ret.difficulty = get_choice_legacy('item_pool', weights)

    ret.item_functionality = get_choice_legacy('item_functionality', weights)

    boss_shuffle = get_choice_legacy('boss_shuffle', weights)
    ret.shufflebosses = get_plando_bosses(boss_shuffle, plando_options)

    ret.enemy_damage = {None: 'default',
                        'default': 'default',
                        'shuffled': 'shuffled',
                        'random': 'chaos', # to be removed
                        'chaos': 'chaos',
                        }[get_choice_legacy('enemy_damage', weights)]

    ret.enemy_health = get_choice_legacy('enemy_health', weights)

    ret.timer = {'none': False,
                 None: False,
                 False: False,
                 'timed': 'timed',
                 'timed_ohko': 'timed-ohko',
                 'ohko': 'ohko',
                 'timed_countdown': 'timed-countdown',
                 'display': 'display'}[get_choice_legacy('timer', weights, False)]

    ret.countdown_start_time = int(get_choice_legacy('countdown_start_time', weights, 10))
    ret.red_clock_time = int(get_choice_legacy('red_clock_time', weights, -2))
    ret.blue_clock_time = int(get_choice_legacy('blue_clock_time', weights, 2))
    ret.green_clock_time = int(get_choice_legacy('green_clock_time', weights, 4))

    ret.dungeon_counters = get_choice_legacy('dungeon_counters', weights, 'default')

    ret.shuffle_prizes = get_choice_legacy('shuffle_prizes', weights, "g")

    ret.required_medallions = [get_choice_legacy("misery_mire_medallion", weights, "random"),
                               get_choice_legacy("turtle_rock_medallion", weights, "random")]

    for index, medallion in enumerate(ret.required_medallions):
        ret.required_medallions[index] = {"ether": "Ether", "quake": "Quake", "bombos": "Bombos", "random": "random"} \
            .get(medallion.lower(), None)
        if not ret.required_medallions[index]:
            raise Exception(f"unknown Medallion {medallion} for {'misery mire' if index == 0 else 'turtle rock'}")

    ret.plando_texts = {}
    if "texts" in plando_options:
        tt = TextTable()
        tt.removeUnwantedText()
        options = weights.get("plando_texts", [])
        for placement in options:
            if roll_percentage(get_choice_legacy("percentage", placement, 100)):
                at = str(get_choice_legacy("at", placement))
                if at not in tt:
                    raise Exception(f"No text target \"{at}\" found.")
                ret.plando_texts[at] = str(get_choice_legacy("text", placement))

    ret.plando_connections = []
    if "connections" in plando_options:
        options = weights.get("plando_connections", [])
        for placement in options:
            if roll_percentage(get_choice_legacy("percentage", placement, 100)):
                ret.plando_connections.append(PlandoConnection(
                    get_choice_legacy("entrance", placement),
                    get_choice_legacy("exit", placement),
                    get_choice_legacy("direction", placement, "both")
                ))

    ret.sprite_pool = weights.get('sprite_pool', [])
    ret.sprite = get_choice_legacy('sprite', weights, "Link")
    if 'random_sprite_on_event' in weights:
        randomoneventweights = weights['random_sprite_on_event']
        if get_choice_legacy('enabled', randomoneventweights, False):
            ret.sprite = 'randomon'
            ret.sprite += '-hit' if get_choice_legacy('on_hit', randomoneventweights, True) else ''
            ret.sprite += '-enter' if get_choice_legacy('on_enter', randomoneventweights, False) else ''
            ret.sprite += '-exit' if get_choice_legacy('on_exit', randomoneventweights, False) else ''
            ret.sprite += '-slash' if get_choice_legacy('on_slash', randomoneventweights, False) else ''
            ret.sprite += '-item' if get_choice_legacy('on_item', randomoneventweights, False) else ''
            ret.sprite += '-bonk' if get_choice_legacy('on_bonk', randomoneventweights, False) else ''
            ret.sprite = 'randomonall' if get_choice_legacy('on_everything', randomoneventweights, False) else ret.sprite
            ret.sprite = 'randomonnone' if ret.sprite == 'randomon' else ret.sprite

            if (not ret.sprite_pool or get_choice_legacy('use_weighted_sprite_pool', randomoneventweights, False)) \
                    and 'sprite' in weights:  # Use sprite as a weighted sprite pool, if a sprite pool is not already defined.
                for key, value in weights['sprite'].items():
                    if key.startswith('random'):
                        ret.sprite_pool += ['random'] * int(value)
                    else:
                        ret.sprite_pool += [key] * int(value)


if __name__ == '__main__':
    import atexit
    confirmation = atexit.register(input, "Press enter to close.")
    main()
    # in case of error-free exit should not need confirmation
    atexit.unregister(confirmation)
