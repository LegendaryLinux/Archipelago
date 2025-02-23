from typing import List
import unittest
from worlds.AutoWorld import World
from Fill import FillError, balance_multiworld_progression, fill_restrictive, distribute_items_restrictive
from BaseClasses import Entrance, LocationProgressType, MultiWorld, Region, RegionType, Item, Location
from worlds.generic.Rules import CollectionRule, locality_rules, set_rule


def generate_multi_world(players: int = 1) -> MultiWorld:
    multi_world = MultiWorld(players)
    multi_world.player_name = {}
    for i in range(players):
        player_id = i+1
        world = World(multi_world, player_id)
        multi_world.game[player_id] = world
        multi_world.worlds[player_id] = world
        multi_world.player_name[player_id] = "Test Player " + str(player_id)
        region = Region("Menu", RegionType.Generic,
                        "Menu Region Hint", player_id, multi_world)
        multi_world.regions.append(region)

    multi_world.set_seed(0)
    multi_world.set_default_common_options()

    return multi_world


class PlayerDefinition(object):
    world: MultiWorld
    id: int
    menu: Region
    locations: List[Location]
    prog_items: List[Item]
    basic_items: List[Item]
    regions: List[Region]

    def __init__(self, world: MultiWorld, id: int, menu: Region, locations: List[Location] = [], prog_items: List[Item] = [], basic_items: List[Item] = []):
        self.world = world
        self.id = id
        self.menu = menu
        self.locations = locations
        self.prog_items = prog_items
        self.basic_items = basic_items
        self.regions = [menu]

    def generate_region(self, parent: Region, size: int, access_rule: CollectionRule = lambda state: True) -> Region:
        region_tag = "_region" + str(len(self.regions))
        region_name = "player" + str(self.id) + region_tag
        region = Region("player" + str(self.id) + region_tag, RegionType.Generic,
                        "Region Hint", self.id, self.world)
        self.locations += generate_locations(size,
                                             self.id, None, region, region_tag)

        entrance = Entrance(self.id, region_name + "_entrance", parent)
        parent.exits.append(entrance)
        entrance.connect(region)
        entrance.access_rule = access_rule

        self.regions.append(region)
        self.world.regions.append(region)

        return region


def fillRegion(world: MultiWorld, region: Region, items: List[Item]) -> List[Item]:
    items = items.copy()
    while len(items) > 0:
        location = region.locations.pop(0)
        region.locations.append(location)
        if location.item:
            return items
        item = items.pop(0)
        world.push_item(location, item, False)
        location.event = item.advancement

    return items


def regionContains(region: Region, item: Item) -> bool:
    for location in region.locations:
        if location.item == item:
            return True

    return False


def generate_player_data(multi_world: MultiWorld, player_id: int, location_count: int = 0, prog_item_count: int = 0, basic_item_count: int = 0) -> PlayerDefinition:
    menu = multi_world.get_region("Menu", player_id)
    locations = generate_locations(location_count, player_id, None, menu)
    prog_items = generate_items(prog_item_count, player_id, True)
    multi_world.itempool += prog_items
    basic_items = generate_items(basic_item_count, player_id, False)
    multi_world.itempool += basic_items

    return PlayerDefinition(multi_world, player_id, menu, locations, prog_items, basic_items)


def generate_locations(count: int, player_id: int, address: int = None, region: Region = None, tag: str = "") -> List[Location]:
    locations = []
    prefix = "player" + str(player_id) + tag + "_location"
    for i in range(count):
        name = prefix + str(i)
        location = Location(player_id, name, address, region)
        locations.append(location)
        region.locations.append(location)
    return locations


def generate_items(count: int, player_id: int, advancement: bool = False, code: int = None) -> List[Item]:
    items = []
    type = "prog" if advancement else ""
    for i in range(count):
        name = "player" + str(player_id) + "_" + type + "item" + str(i)
        items.append(Item(name, advancement, code, player_id))
    return items


def names(objs: list) -> List[str]:
    return map(lambda o: o.name, objs)


class TestFillRestrictive(unittest.TestCase):
    def test_basic_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)

        item0 = player1.prog_items[0]
        item1 = player1.prog_items[1]
        loc0 = player1.locations[0]
        loc1 = player1.locations[1]

        fill_restrictive(multi_world, multi_world.state,
                         player1.locations, player1.prog_items)

        self.assertEqual(loc0.item, item1)
        self.assertEqual(loc1.item, item0)
        self.assertEqual([], player1.locations)
        self.assertEqual([], player1.prog_items)

    def test_ordered_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)
        items = player1.prog_items
        locations = player1.locations

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            items[0].name, player1.id) and state.has(items[1].name, player1.id)
        set_rule(locations[1], lambda state: state.has(
            items[0].name, player1.id))
        fill_restrictive(multi_world, multi_world.state,
                         player1.locations.copy(), player1.prog_items.copy())

        self.assertEqual(locations[0].item, items[0])
        self.assertEqual(locations[1].item, items[1])

    def test_partial_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 3, 2)

        item0 = player1.prog_items[0]
        item1 = player1.prog_items[1]
        loc0 = player1.locations[0]
        loc1 = player1.locations[1]
        loc2 = player1.locations[2]

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            item0.name, player1.id) and state.has(item1.name, player1.id)
        set_rule(loc1, lambda state: state.has(
            item0.name, player1.id))
        # forces a swap
        set_rule(loc2, lambda state: state.has(
            item0.name, player1.id))
        fill_restrictive(multi_world, multi_world.state,
                         player1.locations, player1.prog_items)

        self.assertEqual(loc0.item, item0)
        self.assertEqual(loc1.item, item1)
        self.assertEqual(1, len(player1.locations))
        self.assertEqual(player1.locations[0], loc2)

    def test_minimal_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)

        items = player1.prog_items
        locations = player1.locations

        multi_world.accessibility[player1.id] = 'minimal'
        multi_world.completion_condition[player1.id] = lambda state: state.has(
            items[1].name, player1.id)
        set_rule(locations[1], lambda state: state.has(
            items[0].name, player1.id))

        fill_restrictive(multi_world, multi_world.state,
                         player1.locations.copy(), player1.prog_items.copy())

        self.assertEqual(locations[0].item, items[1])
        # Unnecessary unreachable Item
        self.assertEqual(locations[1].item, items[0])

    def test_reversed_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)

        item0 = player1.prog_items[0]
        item1 = player1.prog_items[1]
        loc0 = player1.locations[0]
        loc1 = player1.locations[1]

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            item0.name, player1.id) and state.has(item1.name, player1.id)
        set_rule(loc1, lambda state: state.has(item1.name, player1.id))
        fill_restrictive(multi_world, multi_world.state,
                         player1.locations, player1.prog_items)

        self.assertEqual(loc0.item, item1)
        self.assertEqual(loc1.item, item0)

    def test_multi_step_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 4, 4)

        items = player1.prog_items
        locations = player1.locations

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            items[2].name, player1.id) and state.has(items[3].name, player1.id)
        set_rule(locations[1], lambda state: state.has(
            items[0].name, player1.id))
        set_rule(locations[2], lambda state: state.has(
            items[1].name, player1.id))
        set_rule(locations[3], lambda state: state.has(
            items[1].name, player1.id))

        fill_restrictive(multi_world, multi_world.state,
                         player1.locations.copy(), player1.prog_items.copy())

        self.assertEqual(locations[0].item, items[1])
        self.assertEqual(locations[1].item, items[2])
        self.assertEqual(locations[2].item, items[0])
        self.assertEqual(locations[3].item, items[3])

    def test_impossible_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)
        items = player1.prog_items
        locations = player1.locations

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            items[0].name, player1.id) and state.has(items[1].name, player1.id)
        set_rule(locations[1], lambda state: state.has(
            items[1].name, player1.id))
        set_rule(locations[0], lambda state: state.has(
            items[0].name, player1.id))

        self.assertRaises(FillError, fill_restrictive, multi_world, multi_world.state,
                          player1.locations.copy(), player1.prog_items.copy())

    def test_circular_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 3, 3)

        item0 = player1.prog_items[0]
        item1 = player1.prog_items[1]
        item2 = player1.prog_items[2]
        loc0 = player1.locations[0]
        loc1 = player1.locations[1]
        loc2 = player1.locations[2]

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            item0.name, player1.id) and state.has(item1.name, player1.id) and state.has(item2.name, player1.id)
        set_rule(loc1, lambda state: state.has(item0.name, player1.id))
        set_rule(loc2, lambda state: state.has(item1.name, player1.id))
        set_rule(loc0, lambda state: state.has(item2.name, player1.id))

        self.assertRaises(FillError, fill_restrictive, multi_world, multi_world.state,
                          player1.locations.copy(), player1.prog_items.copy())

    def test_competing_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, 2, 2)

        item0 = player1.prog_items[0]
        item1 = player1.prog_items[1]
        loc1 = player1.locations[1]

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            item0.name, player1.id) and state.has(item0.name, player1.id) and state.has(item1.name, player1.id)
        set_rule(loc1, lambda state: state.has(item0.name, player1.id)
                 and state.has(item1.name, player1.id))

        self.assertRaises(FillError, fill_restrictive, multi_world, multi_world.state,
                          player1.locations.copy(), player1.prog_items.copy())

    def test_multiplayer_fill(self):
        multi_world = generate_multi_world(2)
        player1 = generate_player_data(multi_world, 1, 2, 2)
        player2 = generate_player_data(multi_world, 2, 2, 2)

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            player1.prog_items[0].name, player1.id) and state.has(
            player1.prog_items[1].name, player1.id)
        multi_world.completion_condition[player2.id] = lambda state: state.has(
            player2.prog_items[0].name, player2.id) and state.has(
            player2.prog_items[1].name, player2.id)

        fill_restrictive(multi_world, multi_world.state, player1.locations +
                         player2.locations, player1.prog_items + player2.prog_items)

        self.assertEqual(player1.locations[0].item, player1.prog_items[1])
        self.assertEqual(player1.locations[1].item, player2.prog_items[1])
        self.assertEqual(player2.locations[0].item, player1.prog_items[0])
        self.assertEqual(player2.locations[1].item, player2.prog_items[0])

    def test_multiplayer_rules_fill(self):
        multi_world = generate_multi_world(2)
        player1 = generate_player_data(multi_world, 1, 2, 2)
        player2 = generate_player_data(multi_world, 2, 2, 2)

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            player1.prog_items[0].name, player1.id) and state.has(
            player1.prog_items[1].name, player1.id)
        multi_world.completion_condition[player2.id] = lambda state: state.has(
            player2.prog_items[0].name, player2.id) and state.has(
            player2.prog_items[1].name, player2.id)

        set_rule(player2.locations[1], lambda state: state.has(
            player2.prog_items[0].name, player2.id))

        fill_restrictive(multi_world, multi_world.state, player1.locations +
                         player2.locations, player1.prog_items + player2.prog_items)

        self.assertEqual(player1.locations[0].item, player2.prog_items[0])
        self.assertEqual(player1.locations[1].item, player2.prog_items[1])
        self.assertEqual(player2.locations[0].item, player1.prog_items[0])
        self.assertEqual(player2.locations[1].item, player1.prog_items[1])

    def test_restrictive_progress(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(multi_world, 1, prog_item_count=25)
        items = player1.prog_items.copy()
        multi_world.completion_condition[player1.id] = lambda state: state.has_all(
            names(player1.prog_items), player1.id)

        player1.generate_region(player1.menu, 5)
        player1.generate_region(player1.menu, 5, lambda state: state.has_all(
            names(items[2:7]), player1.id))
        player1.generate_region(player1.menu, 5, lambda state: state.has_all(
            names(items[7:12]), player1.id))
        player1.generate_region(player1.menu, 5, lambda state: state.has_all(
            names(items[12:17]), player1.id))
        player1.generate_region(player1.menu, 5, lambda state: state.has_all(
            names(items[17:22]), player1.id))

        locations = multi_world.get_unfilled_locations()

        fill_restrictive(multi_world, multi_world.state,
                         locations, player1.prog_items)


class TestDistributeItemsRestrictive(unittest.TestCase):
    def test_basic_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations
        prog_items = player1.prog_items
        basic_items = player1.basic_items

        distribute_items_restrictive(multi_world)

        self.assertEqual(locations[0].item, basic_items[0])
        self.assertFalse(locations[0].event)
        self.assertEqual(locations[1].item, prog_items[0])
        self.assertTrue(locations[1].event)
        self.assertEqual(locations[2].item, prog_items[1])
        self.assertTrue(locations[2].event)
        self.assertEqual(locations[3].item, basic_items[1])
        self.assertFalse(locations[3].event)

    def test_excluded_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations

        locations[1].progress_type = LocationProgressType.EXCLUDED
        locations[2].progress_type = LocationProgressType.EXCLUDED

        distribute_items_restrictive(multi_world)

        self.assertFalse(locations[1].item.advancement)
        self.assertFalse(locations[2].item.advancement)

    def test_non_excluded_item_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations
        basic_items = player1.basic_items

        locations[1].progress_type = LocationProgressType.EXCLUDED
        basic_items[1].never_exclude = True

        distribute_items_restrictive(multi_world)

        self.assertEqual(locations[1].item, basic_items[0])

    def test_too_many_excluded_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations

        locations[0].progress_type = LocationProgressType.EXCLUDED
        locations[1].progress_type = LocationProgressType.EXCLUDED
        locations[2].progress_type = LocationProgressType.EXCLUDED

        self.assertRaises(FillError, distribute_items_restrictive, multi_world)

    def test_non_excluded_item_must_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations
        basic_items = player1.basic_items

        locations[1].progress_type = LocationProgressType.EXCLUDED
        locations[2].progress_type = LocationProgressType.EXCLUDED
        basic_items[0].never_exclude = True
        basic_items[1].never_exclude = True

        self.assertRaises(FillError, distribute_items_restrictive, multi_world)

    def test_priority_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations

        locations[0].progress_type = LocationProgressType.PRIORITY
        locations[3].progress_type = LocationProgressType.PRIORITY

        distribute_items_restrictive(multi_world)

        self.assertTrue(locations[0].item.advancement)
        self.assertTrue(locations[3].item.advancement)

    def test_excess_priority_distribute(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        locations = player1.locations

        locations[0].progress_type = LocationProgressType.PRIORITY
        locations[1].progress_type = LocationProgressType.PRIORITY
        locations[2].progress_type = LocationProgressType.PRIORITY

        distribute_items_restrictive(multi_world)

        self.assertFalse(locations[3].item.advancement)

    def test_multiple_world_priority_distribute(self):
        multi_world = generate_multi_world(3)
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)
        player2 = generate_player_data(
            multi_world, 2, 4, prog_item_count=1, basic_item_count=3)
        player3 = generate_player_data(
            multi_world, 3, 6, prog_item_count=4, basic_item_count=2)

        player1.locations[2].progress_type = LocationProgressType.PRIORITY
        player1.locations[3].progress_type = LocationProgressType.PRIORITY

        player2.locations[1].progress_type = LocationProgressType.PRIORITY

        player3.locations[0].progress_type = LocationProgressType.PRIORITY
        player3.locations[1].progress_type = LocationProgressType.PRIORITY
        player3.locations[2].progress_type = LocationProgressType.PRIORITY
        player3.locations[3].progress_type = LocationProgressType.PRIORITY

        distribute_items_restrictive(multi_world)

        self.assertTrue(player1.locations[2].item.advancement)
        self.assertTrue(player1.locations[3].item.advancement)
        self.assertTrue(player2.locations[1].item.advancement)
        self.assertTrue(player3.locations[0].item.advancement)
        self.assertTrue(player3.locations[1].item.advancement)
        self.assertTrue(player3.locations[2].item.advancement)
        self.assertTrue(player3.locations[3].item.advancement)

    def test_can_remove_locations_in_fill_hook(self):

        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, 4, prog_item_count=2, basic_item_count=2)

        removed_item: list[Item] = []
        removed_location: list[Location] = []

        def fill_hook(progitempool, nonexcludeditempool, localrestitempool, nonlocalrestitempool, restitempool, fill_locations):
            removed_item.append(restitempool.pop(0))
            removed_location.append(fill_locations.pop(0))

        multi_world.worlds[player1.id].fill_hook = fill_hook

        distribute_items_restrictive(multi_world)

        self.assertIsNone(removed_item[0].location)
        self.assertIsNone(removed_location[0].item)

    def test_seed_robust_to_item_order(self):
        mw1 = generate_multi_world()
        gen1 = generate_player_data(
            mw1, 1, 4, prog_item_count=2, basic_item_count=2)
        distribute_items_restrictive(mw1)

        mw2 = generate_multi_world()
        gen2 = generate_player_data(
            mw2, 1, 4, prog_item_count=2, basic_item_count=2)
        mw2.itempool.append(mw2.itempool.pop(0))
        distribute_items_restrictive(mw2)

        self.assertEqual(gen1.locations[0].item, gen2.locations[0].item)
        self.assertEqual(gen1.locations[1].item, gen2.locations[1].item)
        self.assertEqual(gen1.locations[2].item, gen2.locations[2].item)
        self.assertEqual(gen1.locations[3].item, gen2.locations[3].item)

    def test_seed_robust_to_location_order(self):
        mw1 = generate_multi_world()
        gen1 = generate_player_data(
            mw1, 1, 4, prog_item_count=2, basic_item_count=2)
        distribute_items_restrictive(mw1)

        mw2 = generate_multi_world()
        gen2 = generate_player_data(
            mw2, 1, 4, prog_item_count=2, basic_item_count=2)
        reg = mw2.get_region("Menu", gen2.id)
        reg.locations.append(reg.locations.pop(0))
        distribute_items_restrictive(mw2)

        self.assertEqual(gen1.locations[0].item, gen2.locations[0].item)
        self.assertEqual(gen1.locations[1].item, gen2.locations[1].item)
        self.assertEqual(gen1.locations[2].item, gen2.locations[2].item)
        self.assertEqual(gen1.locations[3].item, gen2.locations[3].item)

    def test_can_reserve_advancement_items_for_general_fill(self):
        multi_world = generate_multi_world()
        player1 = generate_player_data(
            multi_world, 1, location_count=5, prog_item_count=5)
        items = player1.prog_items
        multi_world.completion_condition[player1.id] = lambda state: state.has_all(
            names(items), player1.id)

        location = player1.locations[0]
        location.progress_type = LocationProgressType.PRIORITY
        location.item_rule = lambda item: item != items[
            0] and item != items[1] and item != items[2] and item != items[3]

        distribute_items_restrictive(multi_world)

        self.assertEqual(location.item, items[4])

    def test_non_excluded_local_items(self):
        multi_world = generate_multi_world(2)
        player1 = generate_player_data(
            multi_world, 1, location_count=5, basic_item_count=5)
        player2 = generate_player_data(
            multi_world, 2, location_count=5, basic_item_count=5)

        for item in multi_world.get_items():
            item.never_exclude = True

        multi_world.local_items[player1.id].value = set(names(player1.basic_items))
        multi_world.local_items[player2.id].value = set(names(player2.basic_items))
        locality_rules(multi_world, player1.id)
        locality_rules(multi_world, player2.id)

        distribute_items_restrictive(multi_world)

        for item in multi_world.get_items():
            self.assertEqual(item.player, item.location.player)
            self.assertFalse(item.location.event, False)


class TestBalanceMultiworldProgression(unittest.TestCase):
    def assertRegionContains(self, region: Region, item: Item):
        for location in region.locations:
            if location.item and location.item == item:
                return True

        self.fail("Expected " + region.name + " to contain " + item.name +
                  "\n Contains" + str(list(map(lambda location: location.item, region.locations))))

    def setUp(self):
        multi_world = generate_multi_world(2)
        self.multi_world = multi_world
        player1 = generate_player_data(
            multi_world, 1, prog_item_count=2, basic_item_count=40)
        self.player1 = player1
        player2 = generate_player_data(
            multi_world, 2, prog_item_count=2, basic_item_count=40)
        self.player2 = player2

        multi_world.completion_condition[player1.id] = lambda state: state.has(
            player1.prog_items[0].name, player1.id) and state.has(
            player1.prog_items[1].name, player1.id)
        multi_world.completion_condition[player2.id] = lambda state: state.has(
            player2.prog_items[0].name, player2.id) and state.has(
            player2.prog_items[1].name, player2.id)

        items = player1.basic_items + player2.basic_items

        # Sphere 1
        region = player1.generate_region(player1.menu, 20)
        items = fillRegion(multi_world, region, [
            player1.prog_items[0]] + items)

        # Sphere 2
        region = player1.generate_region(
            player1.regions[1], 20, lambda state: state.has(player1.prog_items[0].name, player1.id))
        items = fillRegion(
            multi_world, region, [player1.prog_items[1], player2.prog_items[0]] + items)

        # Sphere 3
        region = player2.generate_region(
            player2.menu, 20, lambda state: state.has(player2.prog_items[0].name, player2.id))
        items = fillRegion(multi_world, region, [
            player2.prog_items[1]] + items)

        multi_world.progression_balancing[player1.id] = True
        multi_world.progression_balancing[player2.id] = True

    def test_balances_progression(self):
        self.assertRegionContains(
            self.player1.regions[2], self.player2.prog_items[0])

        balance_multiworld_progression(self.multi_world)

        self.assertRegionContains(
            self.player1.regions[1], self.player2.prog_items[0])

    def test_ignores_priority_locations(self):
        self.player2.prog_items[0].location.progress_type = LocationProgressType.PRIORITY

        balance_multiworld_progression(self.multi_world)

        self.assertRegionContains(
            self.player1.regions[2], self.player2.prog_items[0])
