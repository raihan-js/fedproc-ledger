<?php
// Runs VETR's own clause-number extraction (FarClauseDetectionService::extractClauseNumbers, protected, via reflection)
// on a JSON list of texts and prints a JSON list of the numbers found. Read-only: VETR is never modified. Only the one
// source file is loaded (its imports are type hints), so neither Composer's autoloader (which demands PHP >= 8.4.1)
// nor the application bootstrap nor a database is needed.
//   VETR_PATH=/path/to/VETR-Framework php scripts/php/vetr_clauses.php cases.json > expected.json
$vetr = getenv('VETR_PATH');
$file = $vetr ? "$vetr/app/Services/FarClauseDetectionService.php" : '';
if (!$file || !is_file($file)) {
    fwrite(STDERR, "set VETR_PATH to a VETR checkout\n");
    exit(2);
}
require $file;
$cases = json_decode(file_get_contents($argv[1]), true);
$service = new App\Services\FarClauseDetectionService();
$method = new ReflectionMethod($service, 'extractClauseNumbers');
$method->setAccessible(true);
$out = [];
foreach ($cases as $text) {
    $out[] = $method->invoke($service, $text);
}
echo json_encode($out, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), "\n";
