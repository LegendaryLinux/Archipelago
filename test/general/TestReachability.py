import unittest

from BaseClasses import CollectionState
from worlds.AutoWorld import AutoWorldRegister

from . import setup_default_world

class TestBase(unittest.TestCase):
    gen_steps = ["generate_early", "create_regions", "create_items", "set_rules", "generate_basic", "pre_fill"]

    def testAllStateCanReachEverything(self):
        for game_name, world_type in AutoWorldRegister.world_types.items():
            # Final Fantasy logic is controlled by finalfantasyrandomizer.com
            if game_name != "Ori and the Blind Forest" and game_name != "Final Fantasy":  # TODO: fix Ori Logic
                with self.subTest("Game", game=game_name):
                    world = setup_default_world(world_type)
                    state = world.get_all_state(False)
                    for location in world.get_locations():
                        with self.subTest("Location should be reached", location=location):
                            self.assertTrue(location.can_reach(state))

    def testEmptyStateCanReachSomething(self):
        for game_name, world_type in AutoWorldRegister.world_types.items():
            # Final Fantasy logic is controlled by finalfantasyrandomizer.com
            if game_name != "Archipelago" and game_name != "Final Fantasy":
                with self.subTest("Game", game=game_name):
                    world = setup_default_world(world_type)
                    state = CollectionState(world)
                    locations = set()
                    for location in world.get_locations():
                        if location.can_reach(state):
                            locations.add(location)
                    self.assertGreater(len(locations), 0,
                                       msg="Need to be able to reach at least one location to get started.")
