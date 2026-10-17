"""Logique métier d'Auto Mail, sans aucune dépendance à l'interface.

- ``addresses`` : lecture des destinataires collés dans n'importe quel format ;
- ``tracking``  : CSV de suivi d'une campagne (lecture, anti-doublon, écriture atomique) ;
- ``message``   : construction des mails (texte / HTML, variables, pièces jointes) ;
- ``gmail``     : SMTP (une connexion, reconnexion auto) et IMAP (libellés, réponses) ;
- ``sender``    : tâche d'envoi en arrière-plan (pause / reprise / annulation) ;
- ``campaigns`` : dossiers de campagne (CSV + brouillon + pièces jointes) ;
- ``settings``  : réglages et mot de passe (keyring).
"""
