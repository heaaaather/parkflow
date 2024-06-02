<?php
session_start();

require __DIR__.'/vendor/autoload.php';

use Kreait\Firebase\Factory;

$factory = (new Factory)
    ->withServiceAccount(__DIR__.'/parkflow-371ef-firebase-adminsdk-hge3z-7bf0223212.json')
    ->withDatabaseUri('https://parkflow-371ef-default-rtdb.firebaseio.com/');

$database = $factory->createDatabase();

// Check if the user is not logged in
if (!isset($_SESSION['id'])) {
    // Redirect to the login page
    header("location: login_new.php");
    exit; // Stop further execution
}

// Fetch user details from the session
$userID = $_SESSION['id'];
// Fetch user details from Firebase Realtime Database
$userRef = $database->getReference('tbl_staffaccount/' . $userID);
$userSnapshot = $userRef->getSnapshot();
$userData = $userSnapshot->getValue();

// Check if user data is retrieved
if (!$userData) {
    // Redirect to the login page if user data is not found
    header("location: login_new.php");
    exit; // Stop further execution
}

// Extract user details
$staffPosition = isset($userData['staffPosition']) ? $userData['staffPosition'] : '';

// Check if the user is not a cashier
if ($staffPosition !== 'cashier') {
    // Redirect to unauthorized access page
    header("location: unauthorized.php");
    exit; // Stop further execution
}
// Define the reference table
$ref_table = "tbl_history";

// Log the visit to the Active Staff page
$actionLocation = 'Cashier Transaction'; // Specify the action location
$actionMessage = "Visited the Transaction page";
logAction($actionLocation , $actionMessage);  // Call logAction
function logAction($actionLocation, $actionMessage) {
    global $database;

    // Set the timezone to Philippines timezone
    date_default_timezone_set('Asia/Manila');

    // Get the current timestamp
    $currentTime = date("Y-m-d H:i:s");

    // Get the total number of logs
    $logCountSnapshot = $database->getReference('tbl_logs')->getSnapshot();
    $logCount = count($logCountSnapshot->getValue());

    // Generate sequential ID
    $logID = $logCount + 1;

    // Push log entry to Firebase with sequential ID
    $database->getReference('tbl_logs/' . $logID)->set([
        'staffID' => $_SESSION['id'],
        'actionLocation' => $actionLocation,
        'actionMessage' => $actionMessage,
        'actionTime' => $currentTime, // Use the current timestamp
    ]);
}

// Define the reference table
$ref_table = "tbl_parking_entries";

// Number of records per page
$records_per_page = 10;

// Get the current page number from URL, default to 1 if not set
$page = isset($_GET['page']) ? (int)$_GET['page'] : 1;
$page = max($page, 1);

// Fetch history data
$reference = $database->getReference($ref_table);
$snapshot = $reference->getSnapshot();
$historyData = $snapshot->getValue();

// Initialize variables for pagination
$total_records = is_array($historyData) ? count($historyData) : 0;
$total_pages = ceil($total_records / $records_per_page);
$start_index = ($page - 1) * $records_per_page;

// Fetch fee data from tbl_fees
$feesReference = $database->getReference('tbl_fees');
$feesSnapshot = $feesReference->getSnapshot();
$feesData = $feesSnapshot->getValue();

// Map parking types to fee keys
$feeMapping = [
    'Regular' => 'flat_rate',
    'Overnight' => 'nightPark',
    'LostTicket' => 'lostTicket'
];

// Initialize the table
$tablehistory = "<table class='table-layout'>
                    <tr>
                        <th>Plate Number</th>
                        <th>Owner Name</th>
                        <th>Time In</th>
                        <th>Time Out</th>
                        <th>Duration</th>
                        <th>Date</th>
                        <th>Parking Type</th>
                        <th>Amount</th>
                        <th>Actions</th>
                    </tr>";

// Check if there is data
if (is_array($historyData) && !empty($historyData)) {
    // Slice the data for the current page
    $current_page_data = array_slice($historyData, $start_index, $records_per_page, true);
    foreach ($current_page_data as $key => $data) {
        if (is_array($data)) {
            $timeIN = isset($data['entryTime']) ? strtotime($data['entryTime']) : 0;
            $timeOUT = isset($data['timeOUT']) ? strtotime($data['timeOUT']) : 0;

            $formattedTimeIN = $timeIN ? date("h:i A", $timeIN) : '';
            $formattedTimeOUT = $timeOUT ? date("h:i A", $timeOUT) : '';

            $durationInSeconds = $timeOUT - $timeIN;
            $hours = floor($durationInSeconds / 3600);
            $minutes = floor(($durationInSeconds % 3600) / 60);

            if ($hours > 0 && $minutes > 0) {
                $durationFormatted = "$hours hours and $minutes minutes";
            } elseif ($hours > 0) {
                $durationFormatted = "$hours hours";
            } else {
                $durationFormatted = "$minutes minutes";
            }

            $plateNumber = isset($data['plateNumber']) ? $data['plateNumber'] : '';
            $customerName = isset($data['customerName']) ? $data['customerName'] : '';
            $entryDate = isset($data['entryDate']) ? $data['entryDate'] : '';
            $parkingType = isset($data['parkingType']) ? $data['parkingType'] : '';

            // Determine the amount based on the parking type
            $amount = 0;
            if (isset($feeMapping[$parkingType]) && isset($feesData[$feeMapping[$parkingType]])) {
                $amount = $feesData[$feeMapping[$parkingType]];
            }

            $tablehistory .= "<tr>";
            $tablehistory .= "<td id='idNums'>" . $plateNumber . "</td>";
            $tablehistory .= "<td>" . $customerName . "</td>";
            $tablehistory .= "<td>" . $formattedTimeIN . "</td>";
            $tablehistory .= "<td>" . $formattedTimeOUT . "</td>";
            $tablehistory .= "<td>" . $durationFormatted . "</td>";
            $tablehistory .= "<td>" . $entryDate . "</td>";
            $tablehistory .= "<td>" . $parkingType . "</td>";
            $tablehistory .= "<td> ₱" . $amount . "</td>";
            $tablehistory .= "<td>
                                <input type='hidden' name='compositeID' value='" . $plateNumber . "|" . $entryDate . "'>
                                <a href='digi_tix.php?plateNumber=" . $plateNumber . "&entryDate=" . $entryDate . "&ACTION=VIEW' target='_blank'>
                                    <button class='btnpdf btn-danger'><span>View</span></button>
                                </a>
                              </td>";
            $tablehistory .= "</tr>";
        }
    }
} else {
    $tablehistory .= "<tr><td colspan='9'>No data found.</td></tr>";
}

$tablehistory .= "</table>";

// Add pagination controls
$tablehistory .= "<div class='pagination'>";
if ($page > 1) {
    $prev_page = $page - 1;
    $tablehistory .= "<a href='?page=$prev_page'>Previous</a>";
}

for ($i = 1; $i <= $total_pages; $i++) {
    if ($i == $page) {
        $tablehistory .= "<a href='?page=$i' class='active'>$i</a>";
    } else {
        $tablehistory .= "<a href='?page=$i'>$i</a>";
    }
}

if ($page < $total_pages) {
    $next_page = $page + 1;
    $tablehistory .= "<a href='?page=$next_page'>Next</a>";
}
$tablehistory .= "</div>";



// Fetch user details from the session
$userID = $_SESSION['id'];

// Fetch user details from Firebase Realtime Database
$userRef = $database->getReference('tbl_staffaccount/' . $userID);
$userSnapshot = $userRef->getSnapshot();
$userData = $userSnapshot->getValue();

// Extract user details
$firstName = isset($userData['firstName']) ? $userData['firstName'] : '';
$lastName = isset($userData['lastName']) ? $userData['lastName'] : '';
$staffPosition = isset($userData['staffPosition']) ? $userData['staffPosition'] : '';
$imagePath = isset($userData['imagePath']) ? $userData['imagePath'] : '';


?>


<!DOCTYPE html>

<html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>History | ParkFlow</title>
        <!--LINKS-->
        <link rel="stylesheet" href="histosrsy.css">
        <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
        <link rel="stylesheet"
            href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />

        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <!--For the icons within the website, i.e., links-->
        <script src="https://kit.fontawesome.com/1d4facf734.js" crossorigin="anonymous"></script>

        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,100;1,200;1,300;1,400;1,500;1,600;1,700;1,800;1,900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,100;0,300;0,400;0,500;0,700;0,900;1,100;1,300;1,400;1,500;1,700;1,900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Marcellus&family=Onest:wght@700&family=Work+Sans&display=swap');
        @font-face {
            font-family: 'NeutraTextTF-Light';
            src: url('path/to/font/NeutraTextTF-Light.ttf') format('truetype');
        }
        /*COLOR HEX*/
        :root {  
        /*COLOR PALETTE:*/
        --black: #000000; 
        --white: #FEFEFE;
        --porcelain: #EEF3F1;

        /*Main Colors*/
        --chambray: #375A7E;
        --greenpea: #236B51;
        --milanored: #B80A12;

        /*Accent Colors*/
        --summergreen: #9EB9AE;
        --gin: #E1EBE6;
        --alizarincrimson: #EC3034;
        --rosewood: #5B0301;
        --milanored: #B80A12;

        /*STA.LU Colors*/
        --stagold: #8C742E;
        --stagreen: #2F4E22;
        --stadark: #2B2F1F;
        --stawhite1: #F9FBF7;
        --stawhite2: #FFF2E8;
        --lightergreen: #2F6922;

        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;   
            font-family: 'Poppins', sans-serif;
            color: var(--black);
        }

        body {
            background-color: var(--porcelain);
        }

        #idNums {
            color: var(--burnt-sienna);
        }

        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            height: 100%;
            width: 260px;
            background-color: var(--stagold);
            z-index: 100;
            transition: all 0.5s ease;
        }

        .sidebar.close {
            width: 78px;
        }

        .sidebar .logo-details {
            height: 90px;
            width: 100%;
            display: flex;
            align-items: center;
            padding-left: 8px;
        }

        .h-line {
            background-color: #1d1b31;
            border: #1d1b31;
            height: 2px;
            opacity: 0.3;
        }

        .sidebar .logo-details i {
            font-size: 26px;
            color: var(--white);
            height: 50px;
            min-width: 68px;
            text-align: center;
            line-height: 50px;
            cursor: pointer;
        }

        .sidebar .logo-details .logo-name {
            font-family: 'Poppins', sans-serif;
              font-size: 24px;
              color: var(--white);
              text-transform: uppercase;
              transition: 0.3s ease;
              transition-delay: 0.1s;
              white-space: nowrap;
              font-weight: 600;
              padding-left: 8px;
        }

        .sidebar.close .logo-details .logo-name {
            transition-delay: 0s;
            opacity: 0;
            pointer-events: none;
            white-space: nowrap;
        }

        .sidebar .nav-links {
            height: calc(100% - 140px);
            padding-top: 20px 0 150px 0;
            overflow-y: auto;
        }

        .sidebar.close .nav-links {
            overflow: visible;
        }

        .sidebar .nav-links::-webkit-scrollbar {
            display: none;
        }
        .sidebar .nav-links li.active {
            background: var(--porcelain);
            position: relative;
            border-radius: 48px 0 0 48px;
          }
        .sidebar .nav-links li.active::before {
            content: '';
            position: absolute;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            top: -40px;
            right: 0;
            box-shadow: 20px 20px 0 var(--porcelain);
            z-index: -1;
         }
        
        .sidebar .nav-links li.active::after {
            content: '';
            position: absolute;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            bottom: -40px;
            right: 0;
            box-shadow: 20px -20px 0 var(--porcelain);
            z-index: -1; 
        }

        .sidebar .nav-links li {
            list-style: none;
            position: relative;
            transition: all 0.4s ease;
        }

        .sidebar .nav-links li:not(.profile-details) a:hover {
            text-decoration: underline;
            color: #fff;
        }


        .sidebar .nav-links li .iocn-link {
            display: flex;
            align-items: center;
            justify-content: space-between;
        } 

        .sidebar.close .nav-links li .iocn-link {
            display: block;
        }

        .sidebar .nav-links li i {
            height: 50px;
            min-width: 82px;
            text-align: center;
            line-height: 50px;
            color: var(--white);
            font-size: 18px;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .sidebar .nav-links .bx-history {
            height: 50px;
              min-width: 82px;
              text-align: center;
              line-height: 50px;
              color: var(--lightergreen);
              font-size: 18px;
              transition: all 0.3s ease;
              cursor: pointer;
          }


            .sidebar .nav-links li.showMenu i.arrow {
                transform: rotate(-180deg);
            }

            .sidebar.close .nav-links i.arrow {
                display: none;
            }

            .sidebar .nav-links li a {
                display: flex;
                align-items: center;
                text-decoration: none;
                
            }

            .sidebar .nav-links li a .link-name {
                font-size: 18px;
                font-weight: 500;
                color: white;
            }
            .sidebar .nav-links li a .link-history {
                font-size: 18px;
              font-weight: 700;
              color: var(--lightergreen);
              
            }
            .sidebar .nav-links li a .link-history:hover {
                text-decoration: underline;
                color: var(--stagreen);
                }
            .sidebar.close .nav-links li a .link-history {
                opacity: 0;
                pointer-events: none;
            }

            .sidebar.close .nav-links li a .link-name {
                opacity: 0;
                pointer-events: none;
            }
            .sidebar .nav-links li .sub-menu {
                padding: 6px 6px 14px 84px;
              background-color: var(--stagreen);
              display: none;
          }
          
          .sidebar .nav-links li.showMenu .sub-menu {
              display: block;
          }

          .sidebar .nav-links li .sub-menu li a {
              color: var(--white);
              font-size: 16px;
              padding: 8px 0;
              white-space: nowrap;
              opacity: 0.6;
              transition: all 0.3s ease;
          }

          .sidebar .nav-links li .sub-menu li a:hover {
              opacity: 1;
          }

          .sidebar.close .nav-links li .sub-menu {
              position: absolute;
              left: 100%;
              top: -10px;
              margin-top: 0;
              padding: 10px 20px;
              border-radius: 0 6px 6px 0;
              opacity: 0;
              display: block;
              pointer-events: none;
              transition: 0s;
          }

            .sidebar.close .nav-links li:hover .sub-menu {
                top: 0;
                opacity: 1;
                pointer-events: auto;
                transition: all 0.4s ease;
            }


            .sidebar .nav-links li .sub-menu .link-name {
                display: none;
            }

            .sidebar.close .nav-links li .sub-menu .link-name {
                display: none;
            }

            .sidebar.close .nav-links li .sub-menu .link-name {
                font-size: 18px;
                opacity: 1;
                display: block;
            }

            .sidebar .nav-links li .sub-menu.blank {
                opacity: 1;
                pointer-events: auto;
                padding: 6px 20px 9px 16px;
                opacity: 0;
                pointer-events: none;
            }

            .sidebar .nav-links li:hover .sub-menu.blank {
                top: 50%;
                transform: translateY(-50%);
            }

            .sidebar .profile-details {
                position: fixed;
                bottom: 0;
                width: 260px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                background-color: var(--stagreen);
                padding: 6px 0;
                transition: all 0.5s ease;
            }
          .sidebar .profile-details .profile-name, .sidebar .profile-details .job {
                color: white;
                font-size: 15px;
                font-weight: 500;
                white-space: nowrap;
            }
            .sidebar .profile-details .job{
                font-size: 12px;
                padding-left: 5px;
                text-transform: capitalize;
            }
          .sidebar.close .profile-details {
              background: none;
          }

          .sidebar.close .profile-details {
              width: 78px;
          }

          .sidebar .profile-details .profile-content {
              display: flex;
              align-items: center;
              
          }

          .sidebar .profile-details img {
                height: 48px;
                width: 48px;
                object-fit: cover;
                border-radius: 16px;
                margin: 0 14px 0 12px;
                background: #1d1b31;
                padding: 4px;
                transition: all 0.5s ease;
            }


          .sidebar .profile-name{
              color: var(--white);
              font-size: 20px;
              margin: 0 5px 0 5%px;
              padding: 6px;
              font-weight: 500;
              white-space: nowrap;
          }

          .sidebar.close .profile-details i,
          .sidebar.close .profile-name, 
          .sidebar.close .profile-details .job {
              display: none;
          }

    
            /***********************************/
            .home-section {
                position: relative;
                background-color: var(--porcelain);
                left: 260px;
                width: calc(100% - 260px);
                transition: all 0.5s ease;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .sidebar.close ~ .home-section {
                left: 78px;
                width: calc(100% - 78px);
            }

            .home-section .home-content {
                height: 70px;
                display: flex;
                align-items: center;
            }

            .home-section .home-content .fa-bars,
            .home-section .home-content .text-title {
                color: var(--stadark);
                font-size: 28px;
            }

            .home-section .home-content .fa-bars {
                margin: 0 15px;
                cursor: pointer;
            }

            .home-section .home-content .text-title {
                font-size: 36px;
                font-weight: 700;
            }

            .bxs-bell {
                color: var(--stagreen);
                font-size: 24px;
                margin-right: 30px;
            }

            /*TABLE LAYOUT ----------*/

            .history-container {
                position: relative;
                background-color: var(--porcelain);
                left: 260px;
                width: calc(100% - 260px);
                transition: all 0.5s ease;
                display: flex;
                align-items: center;
                justify-content: flex-start;
            }

            .sidebar.close ~ .history-container {
                left: 78px;
                width: calc(100% - 78px);
            }

            .staff-table {
                background-color: rgba(255,255,255,0.8);
                overflow: hidden;
                width: 100%;
                height: calc(100vh - 115px);
                margin: 20px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                border-radius: 5px;

            }

            #idColumn {
                width: 50px;
            }

            #actionColumn, #StatColumn, #RPColumn {
                width: 125px;
            }

            #QoHColumn {
                width: 150px;
            }

            .table-layout {
                margin: 20px;
                table-layout: fixed;
                display: table;
                width: calc(100% - 40px);
                border-collapse: collapse;
                border-radius: 5px;
                overflow: hidden;
            }

            .table-layout th, .table-layout td {
                width: 25%;
                padding: 8px;
            }

            .table-layout tr th {
                background-color: var(--greenpea);
                color: white;
            }

            .table-layout tr td {
                background-color: var(--porcelain);
                text-align: center;
            }

            .table-layout tr:nth-child(odd) td {
                background-color: var(--gin);
            }

            /*TOGGLE SWITCH*/
            .toggle-switch {
                position: relative;
                display: inline-block;
                width: 50px;
                height: 22px;
            }

            .toggle-switch input {
                opacity: 0;
                width: 0;
                height: 0;
            }

            .slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: #ccc;
                transition: .4s;
                border-radius: 34px;
            }

            .slider:before {
                position: absolute;
                content: "";
                height: 14px;
                width: 14px;
                left: 4px;
                bottom: 4px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }

            input:checked + .slider {
                background-color: var(--burnt-sienna);
            }

            input:focus + .slider {
                box-shadow: 0 0 1px var(--burnt-sienna);
            }

            input:checked + .slider:before {
                transform: translateX(26px);
            }

            /*SEARCH*/
            .searchNbtn {
                margin: 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .searchNbtn.staffPage {
                justify-content: none;
            }

            .searchBar {
                display: flex;
                align-items: center;
            }

            .searchNbtn input {
                padding: 8px 10px;
                width: 350px;
                border-radius: 5px;
                border: 2px solid var(--greenpea);
            }

            .searchNbtn .bx-search {
                font-size: 20px;
                cursor: pointer;
                font-weight: 500;
                margin: 0 -30px;
            }

            input[type="search"]::-webkit-search-decoration,
            input[type="search"]::-webkit-search-cancel-button,
            input[type="search"]::-webkit-search-results-button,
            input[type="search"]::-webkit-search-results-decoration { display: none; }

            /*ADD ACCOUNT*/
            .addStaff button {
                padding: 8px 10px;
                background-color: var(--burnt-sienna);
                border-radius: 3px;
                border: none;
                cursor: pointer;
            }

            /*BUTTON for EDIT, DELETE*/
            .table-button-edit, .table-button-archive, 
            .table-button-unarchive, .table-button-delete {
                padding: 3px 5px;
                border-radius: 2px;
                font-family: 'Inter', sans-serif;
                font-weight: bold;
                border: none;
                cursor: pointer;
                background-color: var(--hunyadi-yellow);
            }


            .table-button-edit a,
            .table-button-archive a {
                color: white;
            }

            .table-button-edit .bxs-edit, .table-button-archive .bx-archive-in, 
            .table-button-unarchive .bx-archive-out, .table-button-delete .bx-trash {
                color: var(--black);
                font-size: 18px;
                text-align: center;
            }

            .table-button-unarchive, .table-button-archive {
                margin: 0 3px;
            }

            .modal-content h2 {
                color: var(--burnt-sienna);
            }

            .modal-content hr {
                margin-top: 10px;
            }

            /*CONFIRMATION-DELETE*/
            .conf-question p {
                color: var(--burnt-sienna);
                font-size: 22px;
                text-align: center;
                margin: 5px;
            }

            .conf-message p {
                font-size: 14px;
                opacity: 0.7;
                text-align: center;
                margin: 5px;
            }

            .conf-btns {
                display: flex;
                justify-content: center;
            }

            .conf-btn.cancel, .conf-btn.delete {
                padding: 5px;
                margin: 5px 7px;
                border-radius: 5px;
                border: none;
                font-size: 14px;
                cursor: pointer;
            }

            .conf-btn.delete {
                background-color: var(--hunyadi-yellow);
                color: var(--rosewood);
            }

            .conf-btn.delete:hover {
                background-color: #f1aa31;
            }

            .conf-btn.cancel:hover {
                background-color: #e0e0e0;
            }

            .btnQoH {
                margin: 0 10px;
                border: none;
                border-radius: 3px;
                padding: 2px;
                background-color: var(--hunyadi-yellow);
            }

            .bx-plus, .bx-minus {
                width: 800;
                text-align: center;
                font-size: 12px;
                cursor: pointer;
            }

            .btnQoH:hover {
                background-color: #e9ab40;
            }


            /* Add your styles for the modal here */
            .modal {
                display: none;
                position: fixed;
                z-index: 1001; /* Set a higher z-index for the modal */
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: hidden;
                background-color: rgba(0, 0, 0, 0.5);
            }

            .modal-content {
                background-color: #fefefe;
                padding: 20px;
                border: 1px solid #888;
                width: 25%;
                border-radius: 5px;
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
            }

            #editForm, #addAccountForm {
                display: flex;
                flex-direction: column;
                margin-top: 10px;
            }

            .close {
                color: #212B4E;
                float: right;
                font-size: 25px;
                font-weight: bold;
            }

            .close:hover,
            .close:focus {
                color: black;
                text-decoration: none;
                cursor: pointer;
            }

            .hidden {
                display: none;
            }
            .customers-table tr.hidden{
                display: none;
            }
           
            .searchBar {
                display: flex;
                align-items: center;
            }
            .appt-title {
                font-family: 'Roboto', 'Poppins', sans-serif;
                font-size: 24px;
                font-weight: 600;
                color: var(--stadark);
            }
             /**For generate pdf button */
         .generate-pdf input[type="submit"] {
                padding: 8px 10px;
                color: white;
                background-color: #a7eac9;
                border-radius: 3px;
                border: none;
                cursor: pointer;
                width: 120px;
            }
            .fa-sort {
                padding: 0 7px;
                font-size: 14px;
                color: #363636;
                cursor: pointer;
            }
            .btnpdf {
                display: inline-block;
                border-radius: 4px;
                background-color: var(--milanored);
                border: none;
                color: #FFFFFF;
                text-align: center;
                font-size: 14px;
                padding: 5px;
                width: 65px;
                transition: all 0.5s;
                cursor: pointer;
                margin: 5px;
            }
            .btnpdf span {
            cursor: pointer;
            display: inline-block;
            position: relative;
            transition: 0.5s;
            color: #fff;
            font-weight: 500;
            }

            .btnpdf span:after {
            content: '\00bb';
            position: absolute;
            opacity: 0;
            top: 0;
            right: -20px;
            transition: 0.5s;
            }

            .btnpdf:hover span {
            padding-right: 10px;
            }

            .btnpdf:hover span:after {
            opacity: 1;
            right: 0;
            }

            /* PAGNATION */
            .pagination {
                margin-top: 5px;
                margin-bottom: 15px;
            }

            .pagination a {
                display: inline-block;
                padding: 8px 16px;
                text-decoration: none;
                color: #000;
                background-color: #E8BA4E;
                border-radius: 5px;
                margin: 0 5px;
            }

            .pagination a:hover {
                background-color:  #C98F0A;
            }
           
            .doctors-table table tr.hidden {
                display: none;
            }
            .pagination {
                display: flex;
                justify-content: center;
            }

            .pagination a.active {
                background-color:var(--stagold);
                color: white;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        

    <div class="sidebar">
                <div class="logo-details">
                <i class="fas fa-car"></i>
                        <span class="logo-name">ParkFlow</span>
                  
                    </div><!--end of upper portion-->
                 
                    <ul class="nav-links">
                        <li ><!--Dashboard-->
                            <a href="dashboardCashier.php">
                            <i class="bx bxs-dashboard"></i>
                            <span class="link-name">Dashboard</span> 
                            </a>
                            <ul class="sub-menu blank">
                            <li><a class="link-name" href="dashboardCashier.php">Dashboard</a></li>
                        </ul> 
                        </li>

                        <li><!--Parking Slot-->
                            <a href="parkingcashier.php">
                            <i class='bx bxs-parking'></i>
                                <span class="link-name">Parking Slots</span>
                            </a>
                            <ul class="sub-menu blank">
                            <li><a class="link-name" href="parkingcashier.php">Parking Slots</a></li>
                        </ul> 
                        </li>

                 
                        <li class="active"><!--Transaction History-->
                                <a href="historycashier.php">
                                <i class="bx bx-history"></i>
                                    <span class="link-history">Transaction</span>
                                </a> 
                                <ul class="sub-menu blank">
                            <li><a class="link-name" href="historycashier.php">Transaction</a></li>
                        </ul> 
                        </li>

                        <li><!--Profile-->
                                <a href="profileCashier.php">
                                    <i class='bx bx-user' ></i>
                                    <span class="link-name">Profile</span>
                                </a>
                                <ul class="sub-menu blank">
                            <li><a class="link-name" href="profileCashier.php">Profile</a></li>
                        </ul> 
                        </li>

                         <li>
                        <div class="profile-details">
                        <div class="profile-content">
                            <?php
                        // Fetch the image path from the database
                        $imagePath = isset($imagePath) ? $imagePath : '';
                      if ($imagePath) {
                        // Construct the URL to the image file in Google Cloud Storage
                        $imageURL = "https://storage.googleapis.com/parkflow-371ef.appspot.com/$imagePath";
                            // Display the image
                            echo "<img src='$imageURL'  title='$imagePath'>";
                            } else {
                                echo "<img src='default-image.jpg' title='Default Image'>";
                            }
                    ?>
                       </div>
                        <div class="name-job">
                            <?php if (isset($firstName, $lastName, $staffPosition)): ?>
                                <div class="profile-name"><?php echo $firstName . ' ' . $lastName; ?></div>
                                <div class="job"><?php echo $staffPosition; ?></div>
                            <?php endif; ?>
                        </div>
                          <a href="logout.php"><i class='bx bx-log-out' ></i></a>
                        </div>
                    </li>
            </ul>
        </div><!--end of sidebar-->

        <section class="home-section">
            <div class="home-content">
                <i class="fa-solid fa-bars"></i>
                <span class="text-title">Transaction</span>
            </div>
        </section>

        <div class="history-container">
            <div class="staff-table">
            <div class="searchNbtn staffpage">
            <span class="appt-title">Transaction History</span>
                    <div class="searchBar">
                        <input type="search" placeholder="Search here..." name="search-doctor" id="search">
                </div>
                    </div>

                <?php
                    if(isset($tablehistory)) {
                        echo $tablehistory;
                    }
                ?>
            </div>
            </div>
        </div>

<!--Javascript-->
        <script>
            let arrow = document.querySelectorAll(".arrow");

            for (var i = 0; i < arrow.length; i++) {
                arrow[i].addEventListener("click", (e)=>{
                    let arrowParent = e.target.parentElement.parentElement;
                    console.log(arrowParent);

                    arrowParent.classList.toggle("showMenu");
                });
            }

            let sidebar = document.querySelector(".sidebar");
            let sidebarBtn = document.querySelector(".fa-bars");
            console.log(sidebarBtn);
            
            sidebarBtn.addEventListener("click", ()=>{
                    sidebar.classList.toggle("close");
            });


//SEARCH
            document.addEventListener('DOMContentLoaded', function () {
                var searchInput = document.getElementById('search');
                var tableRows = document.querySelectorAll('.staff-table tr');

                searchInput.addEventListener('input', function () {
                    var searchTerm = searchInput.value.toLowerCase();

                    tableRows.forEach(function (row, index) {
                        // Skip the first row (headers)
                        if (index === 0) return;

                        var rowData = row.innerText.toLowerCase();

                        if (rowData.includes(searchTerm)) {
                            row.classList.remove('hidden');
                        } else {
                            row.classList.add('hidden');
                        }
                    });
                });
            });

            //SORT FUNCTION
            var ascending = true;

            function sortTable(columnIndex) {
                var table, rows, switching, i, x, y, shouldSwitch;
                table = document.querySelector('.table-layout');
                switching = true;
                
                while (switching) {
                    switching = false;
                    rows = table.rows;
                    
                    for (i = 1; i < rows.length - 1; i++) {
                        shouldSwitch = false;
                        x = rows[i].getElementsByTagName("td")[columnIndex];
                        y = rows[i + 1].getElementsByTagName("td")[columnIndex];
                        
                        if (ascending) {
                            if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
                                shouldSwitch = true;
                                break;
                            }
                        } else {
                            if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                                shouldSwitch = true;
                                break;
                            }
                        }
                    }
                    
                    if (shouldSwitch) {
                        rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                        switching = true;
                    }
                }
                
                ascending = !ascending;
            }
        </script>
    </body>
</html>
