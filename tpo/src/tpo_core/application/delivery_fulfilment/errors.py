"""Errori provider-neutral del Delivery Fulfilment Writer."""


class DeliveryFulfilmentError(RuntimeError):
    """Errore base del caso d'uso."""


class InvalidDeliveryCommandError(DeliveryFulfilmentError, ValueError):
    """Il command non rispetta il contratto applicativo."""


class DeliveryValidationError(DeliveryFulfilmentError):
    """I fatti persistenti non consentono la pubblicazione richiesta."""


class DeliveryConcurrencyError(DeliveryFulfilmentError):
    """Una expected version non coincide con lo stato bloccato."""


class DeliveryAlreadyPublishedError(DeliveryFulfilmentError):
    """Il public ID CONSEGNA è già stato pubblicato."""


class DeliveryCommitError(DeliveryFulfilmentError):
    """La transazione è fallita con rollback certo."""


class DeliveryCommitOutcomeUncertain(DeliveryFulfilmentError):
    """Il commit è stato richiesto ma la conferma fisica non è certa."""
