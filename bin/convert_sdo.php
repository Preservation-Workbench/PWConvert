#!/usr/bin/php
<?php

$source_file = $argv[1];
echo "SDO-fil: $source_file";
$target_file = $argv[2];
$xml = simplexml_load_file($source_file);

$ns = $xml->getNamespaces(true);

$doc = $xml->SDO->SignedObject->SignersDocument;
$mime = $xml->SDO->SDODataPart->SignatureElement->CMSSignatureElement->SignersDocumentFormat->MimeType;

// $basename = basename($target_file, ".sdo");

if ($mime == 'application/pdf') {
	$content = base64_decode($doc);
	file_put_contents($target_file, $content);
	echo "Fil $source_file konvertert\n";
} else {
	echo "fikk ikke konvertert $source_file med encoding $mime\n";
}
