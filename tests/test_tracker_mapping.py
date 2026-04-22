"""Tests for the shared tracker_mapping module."""

from __future__ import annotations

from osc_tracking.complementary_filter import JOINT_NAMES
from osc_tracking.tracker_mapping import (
    HARITORA_NATIVE_TO_SKELETON,
    SLIMEVR_OSC_INDEX_TO_SKELETON,
    slimevr_osc_addresses,
)


EXPECTED_IMU_BONES = {
    "Hips", "Chest",
    "LeftFoot", "RightFoot",
    "LeftKnee", "RightKnee",
    "LeftElbow", "RightElbow",
}


def test_haritora_native_covers_eight_imu_bones():
    """HaritoraX2 reports 8 trackers — each must map to a skeleton joint."""
    assert set(HARITORA_NATIVE_TO_SKELETON.values()) == EXPECTED_IMU_BONES
    assert len(HARITORA_NATIVE_TO_SKELETON) == 8


def test_slimevr_indices_cover_eight_imu_bones():
    """SlimeVR OSC output assigns indices 1..8 to the same 8 bones."""
    assert set(SLIMEVR_OSC_INDEX_TO_SKELETON.values()) == EXPECTED_IMU_BONES
    assert set(SLIMEVR_OSC_INDEX_TO_SKELETON.keys()) == set(range(1, 9))


def test_both_views_map_to_the_same_bone_set():
    """Native-label and OSC-index views describe the same tracker roster."""
    assert set(HARITORA_NATIVE_TO_SKELETON.values()) == set(
        SLIMEVR_OSC_INDEX_TO_SKELETON.values()
    )


def test_slimevr_osc_addresses_builds_correct_paths():
    addrs = slimevr_osc_addresses()
    # 8 addresses, all of form /tracking/trackers/{id}/rotation
    assert len(addrs) == 8
    for addr, bone in addrs.items():
        assert addr.startswith("/tracking/trackers/")
        assert addr.endswith("/rotation")
        assert bone in EXPECTED_IMU_BONES


def test_mapped_bones_are_all_in_joint_names():
    """Every mapped bone must be a known skeleton joint."""
    for bone in HARITORA_NATIVE_TO_SKELETON.values():
        assert bone in JOINT_NAMES, f"{bone} not in complementary_filter.JOINT_NAMES"
    for bone in SLIMEVR_OSC_INDEX_TO_SKELETON.values():
        assert bone in JOINT_NAMES, f"{bone} not in complementary_filter.JOINT_NAMES"
