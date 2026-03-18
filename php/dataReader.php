<?php
$correct_password = "SuperSecret";
$flask_url = "http://127.0.0.1:5000/store_data";

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    
    $temp = isset($_POST['t']) ? $_POST['t'] : null;
    $count = isset($_POST['count']) ? $_POST['count'] : null;
    $pwd = isset($_POST['pwd']) ? $_POST['pwd'] : null;

    if ($pwd === $correct_password) {
        
        $ch = curl_init($flask_url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query([
            'temperature' => $temp,
            'count' => $count
        ]));
        
        $response = curl_exec($ch);
        curl_close($ch);
        
        echo "Success: Data accepted and forwarded to database.";
    } else {
        // HTTP 401 Unauthorized
        http_response_code(401); 
        echo "Error: Invalid password.";
    }
} else {
    // HTTP 405 Method Not Allowed
    http_response_code(405);
    echo "Error: Only POST requests are allowed.";
}
?>