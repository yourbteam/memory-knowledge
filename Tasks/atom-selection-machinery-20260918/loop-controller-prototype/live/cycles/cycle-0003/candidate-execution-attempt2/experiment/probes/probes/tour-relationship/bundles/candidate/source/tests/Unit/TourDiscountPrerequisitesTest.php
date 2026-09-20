<?php

namespace Tests\Unit;

use Illuminate\Container\Container;
use Illuminate\Database\Capsule\Manager as Capsule;
use Illuminate\Support\Facades\Facade;
use PHPUnit\Framework\TestCase;
use ReflectionClass;

class TourDiscountPrerequisitesTest extends TestCase
{
    private $capsule;
    private $connection;
    private $migration;
    private $reader;
    private $originalTours;
    private $previousFacadeApplication;
    private $facadesConfigured = false;

    protected function setUp(): void
    {
        parent::setUp();

        $container = new Container();
        $this->capsule = new Capsule($container);
        $this->capsule->addConnection([
            'driver' => 'sqlite',
            'database' => ':memory:',
            'prefix' => '',
            'foreign_key_constraints' => true,
        ]);
        $this->connection = $this->capsule->getConnection();
        $this->connection->statement('PRAGMA foreign_keys = ON');
        $container->instance('db', $this->capsule->getDatabaseManager());
        $container->instance('db.schema', $this->connection->getSchemaBuilder());

        $this->previousFacadeApplication = Facade::getFacadeApplication();
        Facade::clearResolvedInstances();
        Facade::setFacadeApplication($container);
        $this->facadesConfigured = true;

        // Only the existing tours fixture is authored here. Relationship storage
        // must be created by the actual product migration.
        $this->connection->statement(<<<'SQL'
CREATE TABLE tours (
    tour_id INTEGER PRIMARY KEY,
    face_rec_version INTEGER DEFAULT 1,
    location_id INTEGER NOT NULL,
    name VARCHAR(191) NOT NULL,
    description TEXT,
    tour_status_id INTEGER NOT NULL,
    tour_type_id INTEGER NOT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    uuid VARCHAR(255) NOT NULL,
    image VARCHAR(255) DEFAULT NULL,
    qr_code TEXT,
    url TEXT,
    isSeachManuallyEnabled INTEGER NOT NULL DEFAULT 1,
    homepageUrl TEXT,
    themeColor VARCHAR(255) NOT NULL DEFAULT '#f4994d',
    isPromoCodePopupEnabled INTEGER NOT NULL DEFAULT 1,
    deliveryFee DECIMAL(15,4) NOT NULL DEFAULT 0.0000,
    hasFullDiscount INTEGER NOT NULL DEFAULT 0,
    payment_provider_id INTEGER NOT NULL DEFAULT 1,
    currency_id INTEGER NOT NULL DEFAULT 1,
    face_rec_first_flow INTEGER NOT NULL DEFAULT 0,
    earlyEmailIntakePopupShow INTEGER NOT NULL DEFAULT 0
)
SQL
        );

        foreach ([101 => 'A', 202 => 'B', 303 => 'C', 404 => 'D'] as $id => $name) {
            $this->connection->table('tours')->insert([
                'tour_id' => $id,
                'location_id' => $id + 1000,
                'name' => 'Fixture tour ' . $name,
                'description' => 'Preserve existing description ' . $name,
                'tour_status_id' => 1,
                'tour_type_id' => 1,
                'created_at' => '2026-09-01 12:00:00',
                'uuid' => 'fixture-tour-' . $name,
                'image' => 'image-' . $name . '.jpg',
                'qr_code' => 'qr-' . $name,
                'url' => '/fixture/' . $name,
                'homepageUrl' => '/home/' . $name,
                'themeColor' => '#123456',
                'deliveryFee' => '12.3400',
                'face_rec_version' => 2,
                'isSeachManuallyEnabled' => 0,
                'isPromoCodePopupEnabled' => 0,
                'hasFullDiscount' => 1,
                'face_rec_first_flow' => 1,
                'earlyEmailIntakePopupShow' => 1,
            ]);
        }
        $this->originalTours = $this->tourSnapshot();

        $configuredRoot = getenv('TAGGABLE_SOURCE_ROOT');
        $root = ($configuredRoot === false || $configuredRoot === '')
            ? dirname(__DIR__, 2)
            : $configuredRoot;
        $root = rtrim($root, '/\\');

        $migrationPath = $root . '/database/migrations/2026_09_14_000001_create_tour_discount_prerequisites.php';
        $servicePath = $root . '/app/Services/TourDiscountPrerequisites.php';
        $this->loadExactClass($migrationPath, 'CreateTourDiscountPrerequisites');
        $this->loadExactClass($servicePath, 'App\\Services\\TourDiscountPrerequisites');

        $this->migration = new \CreateTourDiscountPrerequisites();
        $this->reader = new \App\Services\TourDiscountPrerequisites($this->connection);
        $this->assertToursUnchanged();
    }

    protected function tearDown(): void
    {
        try {
            if ($this->connection !== null) {
                $this->connection->disconnect();
            }
        } finally {
            if ($this->facadesConfigured) {
                Facade::clearResolvedInstances();
                Facade::setFacadeApplication($this->previousFacadeApplication);
            }
            parent::tearDown();
        }
    }

    public function testConfiguredCheckoutTourReturnsItsPrerequisite(): void
    {
        $this->migrateUp();
        $this->configure(202, 101);

        $this->assertSame(true, $this->reader->isConfigured(202));
        $this->assertPrerequisites([101], 202);
        $this->assertToursUnchanged();
    }

    public function testMultiplePrerequisitesArePreserved(): void
    {
        $this->migrateUp();
        $this->configure(202, 101);
        $this->configure(202, 303);
        // An unrelated checkout catches readers that return every stored edge.
        $this->configure(404, 202);

        $this->assertSame(true, $this->reader->isConfigured(202));
        $this->assertPrerequisites([101, 303], 202);
        $this->assertPrerequisites([202], 404);
        $this->assertToursUnchanged();
    }

    public function testUnconfiguredCheckoutTourHasNoPrerequisites(): void
    {
        $this->migrateUp();
        $this->configure(202, 101);

        $this->assertSame(false, $this->reader->isConfigured(404));
        $this->assertPrerequisites([], 404);
        $this->assertToursUnchanged();
    }

    public function testRelationshipDirectionDoesNotConfigureThePrerequisiteTour(): void
    {
        $this->migrateUp();
        $this->configure(202, 101);

        $this->assertSame(true, $this->reader->isConfigured(202));
        $this->assertPrerequisites([101], 202);
        $this->assertSame(false, $this->reader->isConfigured(101));
        $this->assertPrerequisites([], 101);
        $this->assertToursUnchanged();
    }

    public function testIsolatedMigrationRollbackPreservesExistingTours(): void
    {
        $this->assertToursUnchanged();
        $this->migrateUp();
        $this->configure(202, 101);
        $this->configure(202, 303);

        $this->assertSame(true, $this->reader->isConfigured(202));
        $this->assertPrerequisites([101, 303], 202);
        $this->assertToursUnchanged();

        $this->migration->down();

        $this->assertFalse(
            $this->connection->getSchemaBuilder()->hasTable('tour_discount_prerequisites'),
            'Migration down() must remove the relationship table.'
        );
        $this->assertToursUnchanged();
    }

    private function loadExactClass($path, $className): void
    {
        $this->assertFileExists(
            $path,
            'Missing product file: ' . $path . '. Supply the generated product under TAGGABLE_SOURCE_ROOT.'
        );
        if (!class_exists($className, false)) {
            require_once $path;
        }
        $this->assertTrue(
            class_exists($className, false),
            $path . ' must declare ' . $className . '.'
        );
        $reflection = new ReflectionClass($className);
        $this->assertSame(
            realpath($path),
            $reflection->getFileName(),
            'The class must come from the selected product root. Run different roots in separate PHPUnit processes.'
        );
    }

    private function migrateUp(): void
    {
        $this->assertFalse(
            $this->connection->getSchemaBuilder()->hasTable('tour_discount_prerequisites')
        );
        $this->migration->up();
        $schema = $this->connection->getSchemaBuilder();
        $this->assertTrue(
            $schema->hasTable('tour_discount_prerequisites'),
            'Migration up() must create tour_discount_prerequisites.'
        );
        $this->assertTrue($schema->hasColumn('tour_discount_prerequisites', 'checkout_tour_id'));
        $this->assertTrue($schema->hasColumn('tour_discount_prerequisites', 'prerequisite_tour_id'));
        $this->assertToursUnchanged();
    }

    private function configure($checkoutTourId, $prerequisiteTourId): void
    {
        $this->connection->table('tour_discount_prerequisites')->insert([
            'checkout_tour_id' => $checkoutTourId,
            'prerequisite_tour_id' => $prerequisiteTourId,
        ]);
    }

    private function assertPrerequisites(array $expected, $checkoutTourId): void
    {
        $actual = $this->reader->getPrerequisiteTourIds($checkoutTourId);
        $this->assertTrue(is_array($actual), 'getPrerequisiteTourIds() must return an array of integer tour IDs.');
        foreach ($actual as $id) {
            $this->assertTrue(is_int($id), 'Each prerequisite must be an integer tour ID.');
        }
        // Order is unspecified; duplicates and extra/missing IDs still fail.
        sort($expected, SORT_NUMERIC);
        sort($actual, SORT_NUMERIC);
        $this->assertSame($expected, $actual);
    }

    private function tourSnapshot(): array
    {
        return $this->connection->table('tours')->orderBy('tour_id')->get()
            ->map(function ($row) {
                return (array) $row;
            })->all();
    }

    private function assertToursUnchanged(): void
    {
        $this->assertTrue(
            $this->connection->getSchemaBuilder()->hasTable('tours'),
            'The pre-existing tours table must remain present.'
        );
        $this->assertSame(
            $this->originalTours,
            $this->tourSnapshot(),
            'All pre-existing tour rows and recorded column values must remain unchanged.'
        );
    }
}
