<?php 

session_start();
include "fb-con.php";

// Redirect to dashboard if the user is already logged in
if(isset($_SESSION['id'])) {
    header("Location: dashboard.php");
    exit();
}

// Include autoload.php from the Firebase PHP SDK
require __DIR__.'/vendor/autoload.php';

use Kreait\Firebase\Factory;
use Kreait\Firebase\Auth;
use Kreait\Firebase\Exception\Auth\EmailExists;

// Function to initialize Firebase database connection
function initializeFirebase() {
    $factory = (new Factory)
        ->withServiceAccount(__DIR__.'/parkflow-371ef-firebase-adminsdk-hge3z-7bf0223212.json')
        ->withDatabaseUri('https://parkflow-371ef-default-rtdb.firebaseio.com/');

    return $factory->createDatabase();
}

$factory = (new Factory)
    ->withServiceAccount(__DIR__.'/parkflow-371ef-firebase-adminsdk-hge3z-7bf0223212.json')
    ->withDatabaseUri('https://parkflow-371ef-default-rtdb.firebaseio.com/');

$database = $factory->createDatabase();
$auth = $factory->createAuth();

if(isset($_POST['create_acc']))
{
    $first_name = $_POST['fname'];
    $last_name = $_POST['lname'];
    $email_add = $_POST['email'];
    $passcode = $_POST['passcode'];
    $license_plate = $_POST['license'];

    try {
        $userProperties = [
            'email' => $email_add,
            'emailVerified' => false,
            'password' => $passcode,
            'displayName' => $first_name . ' ' . $last_name,
        ];

        $createdUser = $auth->createUser($userProperties);

        if($createdUser) {
            $customerID = $createdUser->uid;
            $userData = [
                'fname' => $first_name,
                'lname' => $last_name,
                'email' => $email_add,
                'passcode' => $passcode,
                'license' => $license_plate,
            ];

            $database->getReference('tbl_customerAcc/' . $customerID)->set($userData);

            $_SESSION['status'] = "User registered successfully!";
            header('Location: login_new.php');
            exit();
        }
    } catch (EmailExists $e) {
        $_SESSION['status'] = "Email already exists.";
        header('Location: login_new.php');
        exit();
    } catch (Exception $e) {
        $_SESSION['status'] = "User registration failed: " . $e->getMessage();
        header('Location: login_new.php');
        exit();
    }
}

?>
