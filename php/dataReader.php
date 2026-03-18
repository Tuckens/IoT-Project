<?php
$temperature = isset($_POST['t']) ? $_POST['t'] : 'Inconnue';
$compteur = isset($_POST['count']) ? $_POST['count'] : 'Inconnu';

error_log("Mesure reçue -> Temp: " . $temperature . "°C | Count: " . $compteur);

$donnees = array(
    'date' => date('Y-m-d H:i:s'),
    'temperature' => $temperature,
    'compteur' => $compteur
);

$ligne_a_sauvegarder = json_encode($donnees) . PHP_EOL;

$chemin_fichier = '/home/boss/data.txt';
file_put_contents($chemin_fichier, $ligne_a_sauvegarder, FILE_APPEND);

echo "Données bien enregistrées sur la Raspberry !";
?>