import unittest

from g1_dancer.mimic import MimicMotion, _display_name


class MimicMotionTests(unittest.TestCase):
    def test_pinyin_names_are_translated_for_display(self):
        cases = {
            "vq_chayao": "Hands on Hips",
            "vq_jingli": "Salute",
            "vq_shuangshoudazhaohu": "Wave with Both Hands",
            "vq_toudingbixin": "Heart above Head",
            "vq_ziwojieshao": "Self Introduction",
            "yingbin": "Welcome Guests",
            "vq_YSKJ_NEWBALEI_008_v1_G1_50hz": "New Ballet",
            "vq_YSKJ_JIXIEWU3_001_XX_b1f11bf1_G1_50hz": "Mechanical Dance 3",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(_display_name(raw), expected)

    def test_unknown_names_keep_the_clean_title_fallback(self):
        self.assertEqual(_display_name("vq_new_robot_move_G1_50hz"), "New Robot Move")

    def test_categories(self):
        cases = [
            (101, "stance", "utility"),
            (401, "faceup_get_up", "recovery"),
            (502, "vq_POPPING1_G1_50hz", "dance"),
            (507, "hello_left_hand", "greeting"),
            (565, "vq_wave_above_head", "greeting"),
            (523, "make_heart_upon_head", "gesture"),
        ]
        for motion_id, name, category in cases:
            with self.subTest(motion_id=motion_id):
                self.assertEqual(MimicMotion(motion_id, name, 1).category, category)


if __name__ == "__main__":
    unittest.main()
