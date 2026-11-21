"""Nodes connected directly to each other, without node array."""

from __future__ import annotations

import math


class Node:
    # Avoid a node dictionary to limit the memory of large trees
    __slots__ = (
        "price",
        "option_value",
        "reach_probability",
        "next_up",
        "next_mid",
        "next_down",
        "up_node",
        "down_node",
        "proba_down",
        "proba_mid",
        "proba_up",
    )

    def __init__(self, price: float) -> None:
        """We create a knot with its price, its probabilities and its initially empty ties"""
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Le prix d'un nœud doit être positif et fini.")
        self.price = price
        self.option_value = 0.0
        # We cumulate the probability of getting here from the root
        self.reach_probability = 0.0

        self.next_up: Node | None = None
        self.next_mid: Node | None = None
        self.next_down: Node | None = None

        self.up_node: Node | None = None
        self.down_node: Node | None = None

        self.proba_down = 0.0
        self.proba_mid = 0.0
        self.proba_up = 0.0

    def upper(self, alpha: float) -> Node:
        """We send the upper neighbour back, creating it only if necessary."""
        # Re-use the existing node for several paths to join
        if self.up_node is None:
            self.up_node = Node(self.price * alpha)
            self.up_node.down_node = self
        return self.up_node

    def lower(self, alpha: float) -> Node:
        """The lower neighbour is returned, only if necessary."""
        if self.down_node is None:
            self.down_node = Node(self.price / alpha)
            self.down_node.up_node = self
        return self.down_node

    def closest(self, target: float, alpha: float) -> Node:
        """We are looking for the price closest to the target on the column."""
        node = self
        while target > node.price * (1.0 + alpha) / 2.0:
            node = node.upper(alpha)

        while target < node.price * (1.0 + 1.0 / alpha) / 2.0:
            node = node.lower(alpha)
        return node

    def top(self) -> Node:
        """Find the highest node of the column to browse it"""
        # You find the top by following the links, without storing the column in a list
        node = self
        while node.up_node is not None:
            node = node.up_node
        return node

    def set_probabilities(self, down: float, mid: float, up: float) -> None:
        """Check and record the three transition probabilities"""

        for probability in (down, mid, up):
            if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError(
                    f"Probabilité invalide ({probability:.6g}), S={self.price:.6g}. "
                    "Cette grille ne convient pas à ces paramètres."
                )

        if not math.isclose(down + mid + up, 1.0, abs_tol=1e-12):
            raise ValueError("La somme des probabilités doit valoir 1.")
        self.proba_down = down
        self.proba_mid = mid
        self.proba_up = up


class TrunkNode(Node):
    """Node of the trunk: adds the link allowing to go back time."""

    __slots__ = ("prev_mid",)

    def __init__(self, price: float, prev_node: TrunkNode | None = None) -> None:
        """Create a trunk node connected to the previous column"""
        super().__init__(price)
        self.prev_mid = prev_node
