<?php
// DIGITAL TICKET GENERATE FOR ADMIN
include 'fb-con.php';
require 'vendor/autoload.php'; // Path to Firebase PHP SDK
include_once('tcpdf.php');

if (isset($_GET['plateNumber']) && isset($_GET['entryDate'])) {
    $plateNumber = $_GET['plateNumber'];
    $entryDate = $_GET['entryDate'];

    $pdfRef = $database->getReference('tbl_parking_entries')
        ->orderByChild('plateNumber')
        ->equalTo($plateNumber)
        ->getSnapshot();

    if ($pdfRef->exists()) {
        $parkingFound = false;
        foreach ($pdfRef->getValue() as $parkingKey => $park_pdf_data) {
            if ($park_pdf_data['entryDate'] == $entryDate) {
                $parkingFound = true;

                // Fetch exit data from tbl_parking_exits
                $exitRef = $database->getReference('tbl_parking_exits')
                    ->orderByChild('plateNumber')
                    ->equalTo($plateNumber)
                    ->getSnapshot();

                if ($exitRef->exists()) {
                    $exitData = current($exitRef->getValue());
                    $exitDate = $exitData['exitDate'];
                    $exitTime = $exitData['exitTime'];

                    // Calculate duration
                    $entryTimestamp = strtotime($park_pdf_data['entryTime']);
                    $exitTimestamp = strtotime($exitTime);
                    $durationSeconds = $exitTimestamp - $entryTimestamp;

                    $durationHours = floor($durationSeconds / 3600);
                    $durationMinutes = floor(($durationSeconds % 3600) / 60);
                    $duration = sprintf("%02dhr %02dmins", $durationHours, $durationMinutes);
                } else {
                    $exitDate = 'N/A';
                    $exitTime = 'N/A';
                    $duration = 'N/A';
                }

                // Fetch fee data from tbl_fees
                $feesReference = $database->getReference('tbl_fees');
                $feesSnapshot = $feesReference->getSnapshot();
                $feesData = $feesSnapshot->getValue();

                $feeMapping = [
                    'Regular' => 'flat_rate',
                    'Overnight' => 'nightPark',
                    'LostTicket' => 'lostTicket'
                ];

                $amount = 0;
                $parkingType = $park_pdf_data['parkingType'];
                if (isset($feeMapping[$parkingType]) && isset($feesData[$feeMapping[$parkingType]])) {
                    $amount = $feesData[$feeMapping[$parkingType]];
                }

                // Generate PDF
                $pdf = new TCPDF('P', 'mm', array(80, 130), true, 'UTF-8', false);
                $pdf->SetCreator(PDF_CREATOR);
                $pdf->setHeaderFont([PDF_FONT_NAME_MAIN, '', PDF_FONT_SIZE_MAIN]);
                $pdf->setFooterFont([PDF_FONT_NAME_DATA, '', PDF_FONT_SIZE_DATA]);
                $pdf->SetDefaultMonospacedFont('courier');
                $pdf->SetFooterMargin(10);
                $pdf->SetMargins(5, 5, 5);
                $pdf->setPrintHeader(false);
                $pdf->setPrintFooter(false);
                $pdf->SetAutoPageBreak(TRUE, 10);
                $pdf->SetFont('courier', '', 10);
                $pdf->AddPage();

                $content = <<<EOD
                <style>
                body {
                    font-family: "Courier New", Courier, monospace;
                    font-size: 9.5px;
                    color: #333;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                .center {
                    text-align: center;
                }
                .bold {
                    font-weight: bold;
                }
                .spacer {
                    line-height: 1.5;
                }
                .logo {
                    width: 40px;
                    height: auto;
                }
                </style>
                <body>
                <table>
                    <tr>
                        <td colspan="2" class="center spacer">
                            <img src="STA_LUCIA_LOGO.jpg" alt="Sta. Lucia Logo" class="logo"><br>
                            <span class="bold">STA. LUCIA EAST GRAND MALL</span>
                        </td>
                    </tr>
                    <tr><td>&nbsp;</td></tr>
                    <tr>
                        <td colspan="2" class="center bold spacer">PARKING TICKET</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">PLATE NUMBER: {$park_pdf_data['plateNumber']}</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">OWNER NAME: {$park_pdf_data['customerName']}</td>
                    </tr>
                    <tr><td>&nbsp;</td></tr>
                    <tr>
                        <td colspan="2" class="center spacer">TIME OF ENTRY: {$park_pdf_data['entryTime']}</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">TIME OF EXIT: {$exitTime}</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">DURATION: {$duration}</td>
                    </tr>
                    <tr><td>&nbsp;</td></tr>
                    <tr>
                        <td colspan="2" class="center bold spacer">PARKING FEES</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">RATE: Php {$amount}.00</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer">DATE: {$exitDate}</td>
                    </tr>
                    <tr><td>&nbsp;</td></tr>
                    <tr>
                        <td colspan="2" class="center bold spacer">Thank you and come again!</td>
                    </tr>
                    <tr><td>&nbsp;</td></tr>
                    <tr>
                        <td colspan="2" class="center spacer" style="font-size: 7px;">Penthouse, Building III, Sta. Lucia East<br>Grand Mall, Cainta, Rizal 1900</td>
                    </tr>
                    <tr>
                        <td colspan="2" class="center spacer" style="font-size: 7px;">+63 02 8681-7332/+63 02 8681-9999</td>
                    </tr>
                </table>
                </body>
EOD;



                $pdf->writeHTML($content);

                $file_name = "INV_" . $park_pdf_data['refID'] . ".pdf";
                ob_end_clean();

                if ($_GET['ACTION'] == 'VIEW') {
                    $pdf->Output($file_name, 'I');
                } elseif ($_GET['ACTION'] == 'DOWNLOAD') {
                    $pdf->Output($file_name, 'D');
                } elseif ($_GET['ACTION'] == 'UPLOAD') {
                    $pdf->Output($file_location . $file_name, 'F');
                    echo "Upload successfully!!";
                }
            }
        }
        if (!$parkingFound) {
            echo 'Record not found for the given plate number and entry date.';
        }
    } else {
        echo 'Record not found for the given plate number.';
    }
} else {
    echo 'Plate number and entry date are required.';
}
?>
