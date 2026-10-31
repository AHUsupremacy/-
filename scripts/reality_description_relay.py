#!/usr/bin/env python3
"""Map remote robot mesh URLs to laptop resources, preserving robot geometry."""

import argparse
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit


def rewrite_description(text, resource_roots):
    missing = set()
    roots = [Path(root).resolve() for root in resource_roots]

    def replace(match):
        uri = match.group()
        path = unquote(urlsplit(uri).path)
        # Both /home/rm/pb2025_ws and versioned release paths contain this suffix.
        if "/share/" not in path:
            missing.add(uri)
            return uri
        package, separator, relative = path.split("/share/", 1)[1].partition("/")
        if not separator or package not in {"pb2025_robot_description", "rmoss_gz_resources"}:
            missing.add(uri)
            return uri
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            missing.add(uri)
            return uri
        for root in roots:
            share = (root / package / "share" / package).resolve()
            candidate = (share / relative).resolve()
            # --symlink-install intentionally puts resources outside install/.
            if candidate.is_file():
                return candidate.as_uri()
        missing.add(uri)
        return uri

    rewritten = re.sub(r'file://[^"<>\s]+', replace, text)
    return rewritten, sorted(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, action="append", required=True)
    args = parser.parse_args()

    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String

    rclpy.init()
    node = rclpy.create_node("gmk_reality_description_relay", enable_rosout=False)
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publisher = node.create_publisher(String, "/gmk_kit/robot_description", qos)

    def callback(message):
        rewritten, missing = rewrite_description(message.data, args.resources)
        publisher.publish(String(data=rewritten))
        if missing:
            node.get_logger().warning("Missing laptop model resources: " + ", ".join(missing[:5]))

    subscription = node.create_subscription(
        String, "/red_standard_robot1/robot_description", callback, qos)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
