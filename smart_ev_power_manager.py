def refresh_ev_charging_state(logger):

    """
    Aggiorna lo stato:
        ev_charging_active

    controllando solo i sensori EV.
    """

    logger.info(
        "[EV MANAGER] refresh_ev_charging_state START"
    )

    try:

        #
        # TODO:
        #
        # - leggere measurement config ID EV
        # - eseguire solo quei measurement
        # - verificare corrente
        # - aggiornare stato globale/db
        #

        logger.info(
            "[EV MANAGER] refresh_ev_charging_state END"
        )

        return True

    except Exception as e:

        logger.exception(
            "[EV MANAGER] refresh_ev_charging_state FAILED | error=%s",
            e,
        )

        return False