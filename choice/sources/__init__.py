# SPDX-License-Identifier: AGPL-3.0-only
"""Pluggable deck sources."""

from choice.sources.registry import build_source, source_types

__all__ = ["build_source", "source_types"]
