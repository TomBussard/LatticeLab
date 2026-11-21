"""Nœuds reliés directement entre eux, sans tableau de nœuds."""

from __future__ import annotations

import math


class Node:
    # On évite un dictionnaire par nœud pour limiter la mémoire des grands arbres
    __slots__ = ("price", "option_value", "reach_probability", "next_up", "next_mid", "next_down",
                 "up_node", "down_node", "proba_down", "proba_mid", "proba_up")

    def __init__(self, price: float) -> None:
        """On crée un nœud avec son prix, ses probabilités et ses liens initialement vides"""
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Le prix d'un nœud doit être positif et fini.")
        self.price = price
        self.option_value = 0.0
        # On cumule la probabilité d'arriver ici depuis la racine
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
        """On renvoie le voisin supérieur, en le créant seulement si nécessaire"""
        # On réutilise le nœud existant pour que plusieurs chemins se rejoignent
        if self.up_node is None:
            self.up_node = Node(self.price * alpha)
            self.up_node.down_node = self
        return self.up_node

    def lower(self, alpha: float) -> Node:
        """On renvoie le voisin inférieur, en le créant seulement si nécessaire"""
        if self.down_node is None:
            self.down_node = Node(self.price / alpha)
            self.down_node.up_node = self
        return self.down_node

    def closest(self, target: float, alpha: float) -> Node:
        """On cherche le prix le plus proche de la cible sur la colonne"""
        node = self
        while target > node.price * (1.0 + alpha) / 2.0:
            node = node.upper(alpha)

        while target < node.price * (1.0 + 1.0 / alpha) / 2.0:
            node = node.lower(alpha)
        return node

    def top(self) -> Node:
        """On retrouve le nœud le plus haut de la colonne pour la parcourir"""
        # On retrouve le sommet en suivant les liens, sans stocker la colonne dans une liste
        node = self
        while node.up_node is not None:
            node = node.up_node
        return node

    def set_probabilities(self, down: float, mid: float, up: float) -> None:
        """On vérifie et on enregistre les trois probabilités de transition"""

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
    """Nœud du tronc : ajoute le lien permettant de remonter le temps."""

    __slots__ = ("prev_mid",)

    def __init__(self, price: float, prev_node: TrunkNode | None = None) -> None:
        """On crée un nœud de tronc relié à la colonne précédente"""
        super().__init__(price)
        self.prev_mid = prev_node
